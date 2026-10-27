"""Reglas de negocio de las ventas (HU-04, SRS 3.1.3 y 3.3.3).

Una compra es un carrito: vehículos (el cliente escoge el modelo y el sistema asigna las
unidades) y accesorios o repuestos (por cantidad). Al crearla:

1. **Se bloquean las filas** de las unidades de esos modelos y de esos productos, en el
   orden global del sistema (ver ``bloquear_inventario``). De paso se expiran las compras y
   reservas vencidas que las apartaban (CLAUDE.md 7.1, regla 2).
2. **Se valida todo antes de tocar nada**: una unidad se vende solo si está ``disponible``
   y no tiene alquileres activos ni futuros; un producto, solo si alcanza el stock.
3. **Se aparta lo comprado** por 15 minutos: las unidades pasan a ``reservado`` y el stock
   se descuenta. Si no se paga a tiempo, la compra expira y todo se devuelve.

Al aprobarse el pago, las unidades pasan a ``vendido``. Si alguna dejó de estar apartada
(por ejemplo, entró en mantenimiento), la compra **no se completa**: se cancela, se devuelve
lo apartado y se registra la devolución del dinero (decisión 2 del Sprint 2).
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.auditoria import registrar_auditoria
from app.comun import fechas
from app.comun.errores import PermisoDenegado
from app.comun.paginacion import ParametrosPagina, ResultadoPagina, paginar
from app.modulos.alquileres.modelos import ESTADOS_ACTIVOS, Alquiler
from app.modulos.alquileres.servicio import expirar_vencidos as expirar_alquileres_vencidos
from app.modulos.inventario.modelos import EstadoVehiculo, Producto, Vehiculo
from app.modulos.inventario.servicio import (
    bloquear_inventario,
    cambiar_estado_vehiculo,
    obtener_modelo_visible,
)
from app.modulos.pagos import servicio as pagos
from app.modulos.pagos.modelos import EstadoPago, MetodoPago, Pago, TipoPago
from app.modulos.pagos.pasarela import PasarelaPagos
from app.modulos.usuarios.modelos import Rol, Usuario
from app.modulos.ventas.esquemas import VentaCrear
from app.modulos.ventas.estados import validar_transicion
from app.modulos.ventas.excepciones import (
    ModeloNoSeVende,
    ProductoNoEncontrado,
    SinUnidadesParaVenta,
    StockInsuficiente,
    VentaExpirada,
    VentaNoCancelable,
    VentaNoEncontrada,
)
from app.modulos.ventas.liberacion import bloquear_y_expirar, cambiar_estado_venta, liberar_venta
from app.modulos.ventas.modelos import EstadoVenta, ItemVenta, Venta

registro = logging.getLogger(__name__)

# Bloqueo temporal mientras el cliente paga (decisión del 29/09/2026, igual que HU-03).
MINUTOS_BLOQUEO = 15

ROLES_DE_MOSTRADOR = frozenset({Rol.ADMINISTRADOR, Rol.OPERADOR})


@dataclass(frozen=True)
class ResultadoPagoVenta:
    venta: Venta
    pago: Pago
    devolucion: Pago | None


@dataclass(frozen=True)
class DatosComprobante:
    venta: Venta
    pago: Pago | None
    metodo: str | None


# --- Lógica pura -----------------------------------------------------------------------------


def esta_vencida(venta: Venta, momento: datetime) -> bool:
    """Una ``pendiente_pago`` cuyo bloqueo de 15 minutos ya pasó."""
    return (
        venta.estado == EstadoVenta.PENDIENTE_PAGO
        and venta.expira_en is not None
        and venta.expira_en <= momento
    )


def estado_vigente(venta: Venta, momento: datetime) -> EstadoVenta:
    """Una pendiente vencida se muestra ``expirada`` aunque nadie la haya marcado aún."""
    return EstadoVenta.EXPIRADA if esta_vencida(venta, momento) else venta.estado


# --- Piezas internas -------------------------------------------------------------------------


def _exigir_rol(usuario: Usuario, permitidos: frozenset[Rol]) -> None:
    # Las rutas ya lo exigen; el servicio lo repite para que ninguna llamada futura lo salte.
    if usuario.rol not in permitidos:
        raise PermisoDenegado()


def _del_cliente(venta: Venta, cliente: Usuario) -> None:
    # A otro cliente se le dice "no existe", no "no es tuya": no se revela qué ids existen.
    if venta.cliente_id != cliente.id:
        raise VentaNoEncontrada()


def _bloquear_venta(
    sesion: Session, venta_id: int
) -> tuple[Venta, dict[int, Vehiculo], dict[int, Producto]]:
    """Bloquea las unidades y productos de la venta (orden global) y luego la venta."""
    items = sesion.execute(
        select(ItemVenta.vehiculo_id, ItemVenta.producto_id).where(ItemVenta.venta_id == venta_id)
    ).all()
    if not items:  # toda venta tiene al menos un ítem
        raise VentaNoEncontrada()
    vehiculos, productos = bloquear_inventario(
        sesion,
        [v for v, _ in items if v is not None],
        [p for _, p in items if p is not None],
    )
    venta = sesion.scalars(
        select(Venta)
        .where(Venta.id == venta_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    return venta, vehiculos, productos


def _expirar_y_avisar(sesion, venta, vehiculos, productos) -> None:
    """Marca expirada la venta vencida, devuelve lo apartado, confirma y avisa al cliente."""
    liberar_venta(
        sesion, venta, EstadoVenta.EXPIRADA, None, "Bloqueo vencido", vehiculos, productos
    )
    sesion.commit()
    raise VentaExpirada()


def _con_detalle():
    return (
        selectinload(Venta.items).joinedload(ItemVenta.vehiculo).joinedload(Vehiculo.modelo),
        selectinload(Venta.items).joinedload(ItemVenta.producto),
    )


# --- Cliente: comprar, pagar, cancelar -------------------------------------------------------


def crear_venta(
    sesion: Session,
    cliente: Usuario,
    datos: VentaCrear,
    *,
    momento: datetime | None = None,
) -> Venta:
    """Crea la compra en ``pendiente_pago`` y aparta lo comprado por 15 minutos."""
    _exigir_rol(cliente, frozenset({Rol.CLIENTE}))
    momento = momento or fechas.ahora()

    modelos = {}
    for item in datos.vehiculos:
        modelo = obtener_modelo_visible(sesion, item.modelo_id)
        if modelo.precio_venta is None:
            raise ModeloNoSeVende(f"«{modelo.nombre}» solo se alquila, no está a la venta.")
        modelos[modelo.id] = modelo
    producto_ids = [i.producto_id for i in datos.productos]
    activos = set(
        sesion.scalars(select(Producto.id).where(Producto.id.in_(producto_ids), Producto.activo))
    )
    if len(activos) != len(producto_ids):
        raise ProductoNoEncontrado()

    unidad_ids = sesion.scalars(select(Vehiculo.id).where(Vehiculo.modelo_id.in_(modelos))).all()
    vehiculos, productos = bloquear_y_expirar(sesion, momento, unidad_ids, producto_ids)
    expirar_alquileres_vencidos(sesion, momento, unidad_ids)
    # No se vende una unidad con alquileres pendientes, confirmados o en curso (CLAUDE.md 7.1).
    con_alquiler = set(
        sesion.scalars(
            select(Alquiler.vehiculo_id).where(
                Alquiler.vehiculo_id.in_(unidad_ids), Alquiler.estado.in_(ESTADOS_ACTIVOS)
            )
        )
    )

    # Validar todo antes de tocar nada.
    venta = Venta(
        cliente_id=cliente.id,
        estado=EstadoVenta.PENDIENTE_PAGO,
        expira_en=momento + timedelta(minutes=MINUTOS_BLOQUEO),
        valor_envio=0,  # el domicilio se suma con HU-06
    )
    apartadas: list[Vehiculo] = []
    for item in datos.vehiculos:
        modelo = modelos[item.modelo_id]
        libres = [
            vehiculos[i]
            for i in sorted(unidad_ids)
            if vehiculos[i].modelo_id == modelo.id
            and vehiculos[i].estado == EstadoVehiculo.DISPONIBLE
            and i not in con_alquiler
        ]
        if len(libres) < item.cantidad:
            raise SinUnidadesParaVenta(
                f"Pediste {item.cantidad} unidad(es) de «{modelo.nombre}» y hay "
                f"{len(libres)} disponible(s) para la venta."
            )
        for unidad in libres[: item.cantidad]:
            apartadas.append(unidad)
            venta.items.append(
                ItemVenta(
                    vehiculo_id=unidad.id,
                    cantidad=1,
                    precio_unitario=modelo.precio_venta,
                    subtotal=modelo.precio_venta,
                )
            )
    for item in datos.productos:
        producto = productos[item.producto_id]
        if producto.stock < item.cantidad:
            raise StockInsuficiente(
                f"Pediste {item.cantidad} de «{producto.nombre}» y quedan {producto.stock}."
            )
        venta.items.append(
            ItemVenta(
                producto_id=producto.id,
                cantidad=item.cantidad,
                precio_unitario=producto.precio_venta,
                subtotal=item.cantidad * producto.precio_venta,
            )
        )
    venta.subtotal = sum(i.subtotal for i in venta.items)
    venta.total = venta.subtotal + venta.valor_envio
    sesion.add(venta)
    sesion.flush()

    # Apartar: unidades a "reservado" y stock descontado.
    for unidad in apartadas:
        motivo = f"Apartada por la venta #{venta.id}"
        cambiar_estado_vehiculo(sesion, unidad, EstadoVehiculo.RESERVADO, cliente, motivo)
    for item in datos.productos:
        productos[item.producto_id].stock -= item.cantidad
    registrar_auditoria(
        sesion,
        usuario_id=cliente.id,
        accion="crear",
        entidad="ventas",
        entidad_id=venta.id,
        despues={
            "vehiculos": [u.id for u in apartadas],
            "productos": {str(i.producto_id): i.cantidad for i in datos.productos},
            "total": venta.total,
        },
    )
    sesion.commit()
    return venta


def pagar_venta(
    sesion: Session,
    venta_id: int,
    cliente: Usuario,
    metodo_codigo: str,
    pasarela: PasarelaPagos,
    *,
    momento: datetime | None = None,
) -> ResultadoPagoVenta:
    """Cobra el total de una compra pendiente.

    - Aprobado y todas las unidades apartadas: la compra queda ``pagada`` y las unidades
      ``vendido``.
    - Aprobado pero alguna unidad ya no está apartada (entró en mantenimiento): la compra se
      cancela, se devuelve lo apartado y se registra la devolución del dinero.
    - Rechazado: la compra sigue pendiente; el cliente puede reintentar a tiempo.
    """
    momento = momento or fechas.ahora()
    venta, vehiculos, productos = _bloquear_venta(sesion, venta_id)
    _del_cliente(venta, cliente)
    if esta_vencida(venta, momento):
        _expirar_y_avisar(sesion, venta, vehiculos, productos)
    validar_transicion(venta.estado, EstadoVenta.PAGADA)
    metodo = pagos.obtener_metodo_activo(sesion, metodo_codigo)

    pago = pagos.cobrar(sesion, pasarela, venta.total, metodo, momento, venta_id=venta.id)
    devolucion = None
    if pago.estado == EstadoPago.APROBADO:
        unidades = [vehiculos[i.vehiculo_id] for i in venta.items if i.vehiculo_id is not None]
        no_apartadas = [u for u in unidades if u.estado != EstadoVehiculo.RESERVADO]
        if no_apartadas:
            devolucion = _cancelar_con_devolucion(
                sesion, venta, pago, no_apartadas, vehiculos, productos
            )
        else:
            for unidad in unidades:
                motivo = f"Venta #{venta.id} pagada"
                cambiar_estado_vehiculo(sesion, unidad, EstadoVehiculo.VENDIDO, cliente, motivo)
            cambiar_estado_venta(sesion, venta, EstadoVenta.PAGADA, cliente, "Pago aprobado")
    sesion.commit()
    return ResultadoPagoVenta(venta, pago, devolucion)


def _cancelar_con_devolucion(
    sesion: Session,
    venta: Venta,
    pago: Pago,
    no_apartadas: list[Vehiculo],
    vehiculos: dict[int, Vehiculo],
    productos: dict[int, Producto],
) -> Pago:
    """Decisión 2 del Sprint 2: la compra no se completa y se devuelve el dinero.

    El aviso al administrador es la lista ``GET /ventas/devoluciones-pendientes`` (más un
    registro de advertencia en el log): no hay notificaciones en el MVP (HU-14 está fuera).
    """
    detalle = ", ".join(f"{u.codigo} ({u.estado.value})" for u in no_apartadas)
    motivo = (
        f"Unidad(es) {detalle} dejaron de estar apartadas antes de aprobarse el pago. "
        "La compra no se completa y se devuelve el dinero."
    )
    venta.motivo_cancelacion = motivo
    liberar_venta(sesion, venta, EstadoVenta.CANCELADA, None, motivo, vehiculos, productos)
    devolucion = pagos.registrar_devolucion(sesion, pago, motivo)
    registro.warning(
        "Compra cancelada con devolución pendiente: el administrador debe atenderla",
        extra={"venta_id": venta.id, "pago_id": pago.id, "devolucion_id": devolucion.id},
    )
    return devolucion


def cancelar_venta(
    sesion: Session,
    venta_id: int,
    cliente: Usuario,
    motivo: str | None = None,
    *,
    momento: datetime | None = None,
) -> Venta:
    """El cliente desiste de una compra sin pagar. Devuelve el stock y suelta las unidades."""
    momento = momento or fechas.ahora()
    venta, vehiculos, productos = _bloquear_venta(sesion, venta_id)
    _del_cliente(venta, cliente)
    if esta_vencida(venta, momento):
        _expirar_y_avisar(sesion, venta, vehiculos, productos)
    if venta.estado != EstadoVenta.PENDIENTE_PAGO:
        raise VentaNoCancelable()
    venta.motivo_cancelacion = motivo
    liberar_venta(sesion, venta, EstadoVenta.CANCELADA, cliente, motivo or "", vehiculos, productos)
    sesion.commit()
    return venta


# --- Consultas -------------------------------------------------------------------------------


def listar_ventas(
    sesion: Session,
    parametros: ParametrosPagina,
    *,
    cliente_id: int | None = None,
    estado: EstadoVenta | None = None,
    momento: datetime | None = None,
) -> ResultadoPagina:
    """Ventas de la más reciente a la más antigua. El cliente solo pide las suyas.

    El filtro ``estado`` usa el estado vigente: una pendiente vencida cuenta como expirada.
    """
    momento = momento or fechas.ahora()
    consulta = select(Venta).options(*_con_detalle()).order_by(Venta.id.desc())
    if cliente_id is not None:
        consulta = consulta.where(Venta.cliente_id == cliente_id)
    if estado is not None:
        vencida = and_(Venta.estado == EstadoVenta.PENDIENTE_PAGO, Venta.expira_en <= momento)
        if estado == EstadoVenta.EXPIRADA:
            consulta = consulta.where(or_(Venta.estado == estado, vencida))
        elif estado == EstadoVenta.PENDIENTE_PAGO:
            consulta = consulta.where(Venta.estado == estado, Venta.expira_en > momento)
        else:
            consulta = consulta.where(Venta.estado == estado)
    return paginar(sesion, consulta, parametros)


def listar_devoluciones_pendientes(
    sesion: Session, parametros: ParametrosPagina
) -> ResultadoPagina:
    """Ventas con una devolución de dinero registrada y aún sin ejecutar (decisión 2).

    Es el aviso al administrador. La devolución se ejecuta en la pasarela con HU-05.
    """
    con_devolucion = select(Pago.venta_id).where(
        Pago.tipo == TipoPago.COMPENSACION, Pago.estado == EstadoPago.PENDIENTE
    )
    consulta = (
        select(Venta)
        .where(Venta.id.in_(con_devolucion))
        .options(*_con_detalle())
        .order_by(Venta.id)
    )
    return paginar(sesion, consulta, parametros)


def obtener_venta(sesion: Session, venta_id: int, usuario: Usuario) -> Venta:
    """Una venta. El cliente solo ve las suyas; el mostrador, todas."""
    venta = sesion.scalars(
        select(Venta).where(Venta.id == venta_id).options(*_con_detalle())
    ).one_or_none()
    if venta is None:
        raise VentaNoEncontrada()
    if usuario.rol == Rol.CLIENTE:
        _del_cliente(venta, usuario)
    else:
        _exigir_rol(usuario, ROLES_DE_MOSTRADOR)
    return venta


def obtener_comprobante(sesion: Session, venta_id: int, usuario: Usuario) -> DatosComprobante:
    """Datos del comprobante preliminar: la venta y su último cobro (aprobado, si hay)."""
    venta = sesion.scalars(
        select(Venta)
        .where(Venta.id == venta_id)
        .options(*_con_detalle(), joinedload(Venta.cliente))
    ).one_or_none()
    if venta is None:
        raise VentaNoEncontrada()
    if usuario.rol == Rol.CLIENTE:
        _del_cliente(venta, usuario)
    else:
        _exigir_rol(usuario, ROLES_DE_MOSTRADOR)
    pago = sesion.scalars(
        select(Pago)
        .where(Pago.venta_id == venta.id, Pago.tipo == TipoPago.COBRO)
        .order_by((Pago.estado == EstadoPago.APROBADO).desc(), Pago.id.desc())
        .limit(1)
    ).first()
    metodo = sesion.get(MetodoPago, pago.metodo_pago_id).nombre if pago else None
    return DatosComprobante(venta, pago, metodo)
