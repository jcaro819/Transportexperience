"""Servicio de ventas (HU-04): comprar, pagar, cancelar, expirar y comprobante.

Contra Postgres, con "ahora" fijo. La concurrencia se prueba en ``test_concurrencia.py``.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.auditoria import RegistroAuditoria
from app.comun.errores import PermisoDenegado
from app.comun.paginacion import ParametrosPagina
from app.modulos.alquileres import servicio as alquileres
from app.modulos.alquileres.excepciones import SinUnidadesDisponibles
from app.modulos.alquileres.modelos import EstadoAlquiler
from app.modulos.inventario import servicio as inventario
from app.modulos.inventario.esquemas import CierreNovedad
from app.modulos.inventario.excepciones import NoPuedeVolverAServicio
from app.modulos.inventario.modelos import CategoriaProducto, EstadoVehiculo, NovedadVehiculo
from app.modulos.pagos import procesamiento
from app.modulos.pagos.esquemas import PagoCrear
from app.modulos.pagos.modelos import EstadoPago, MetodoPago, Pago, TipoPago
from app.modulos.pagos.pasarela import PasarelaFalsa
from app.modulos.usuarios.modelos import Rol
from app.modulos.ventas import servicio
from app.modulos.ventas.esquemas import VentaCrear
from app.modulos.ventas.excepciones import (
    ModeloNoSeVende,
    ProductoNoEncontrado,
    SinUnidadesParaVenta,
    StockInsuficiente,
    TransicionDeVentaInvalida,
    VentaExpirada,
    VentaNoCancelable,
    VentaNoEncontrada,
)
from app.modulos.ventas.modelos import EstadoVenta, Venta

MOMENTO = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
HOY = date(2026, 11, 2)
PRECIO = 2_000_000


@pytest.fixture(autouse=True)
def metodos_pago(sesion) -> None:
    sesion.add(MetodoPago(codigo="tarjeta", nombre="Tarjeta de crédito o débito"))
    sesion.flush()


@pytest.fixture
def modelo(fabrica):
    return fabrica.modelo(tarifa_diaria=40_000, precio_venta=PRECIO)


@pytest.fixture
def cliente(fabrica):
    return fabrica.cliente()


@pytest.fixture
def operador(crear_usuario):
    return crear_usuario(Rol.OPERADOR)


def _carrito(vehiculos=(), productos=()) -> VentaCrear:
    return VentaCrear(
        vehiculos=[{"modelo_id": m.id, "cantidad": c} for m, c in vehiculos],
        productos=[{"producto_id": p.id, "cantidad": c} for p, c in productos],
    )


def _comprar(sesion, cliente, vehiculos=(), productos=(), momento=MOMENTO) -> Venta:
    return servicio.crear_venta(sesion, cliente, _carrito(vehiculos, productos), momento=momento)


def _pagar(sesion, venta, cliente, *, aprueba=True, momento=MOMENTO):
    pasarela = PasarelaFalsa(EstadoPago.APROBADO if aprueba else EstadoPago.RECHAZADO)
    return procesamiento.pagar(
        sesion,
        cliente,
        PagoCrear(metodo_pago="tarjeta"),
        pasarela,
        venta_id=venta.id,
        momento=momento,
    )


# --- Comprar ----------------------------------------------------------------------------


def test_comprar_un_vehiculo_lo_aparta_15_minutos(sesion, fabrica, modelo, cliente) -> None:
    unidad = fabrica.vehiculo(modelo)

    venta = _comprar(sesion, cliente, [(modelo, 1)])

    assert venta.estado == EstadoVenta.PENDIENTE_PAGO
    assert venta.expira_en == MOMENTO + timedelta(minutes=15)
    assert [i.vehiculo_id for i in venta.items] == [unidad.id]
    assert (venta.subtotal, venta.valor_envio, venta.total) == (PRECIO, 0, PRECIO)
    assert unidad.estado == EstadoVehiculo.RESERVADO


def test_comprar_productos_descuenta_el_stock(sesion, fabrica, cliente) -> None:
    casco = fabrica.producto(stock=5, precio_venta=120_000)

    venta = _comprar(sesion, cliente, productos=[(casco, 2)])

    assert casco.stock == 3
    [item] = venta.items
    assert (item.cantidad, item.precio_unitario, item.subtotal) == (2, 120_000, 240_000)
    assert venta.total == 240_000


def test_carrito_mixto_suma_vehiculos_y_productos(sesion, fabrica, modelo, cliente) -> None:
    fabrica.vehiculo(modelo)
    fabrica.vehiculo(modelo)
    cargador = fabrica.producto(precio_venta=80_000)

    venta = _comprar(sesion, cliente, [(modelo, 2)], [(cargador, 1)])

    assert len(venta.items) == 3
    assert venta.total == 2 * PRECIO + 80_000


def test_stock_insuficiente_no_cambia_nada(sesion, fabrica, modelo, cliente) -> None:
    unidad = fabrica.vehiculo(modelo)
    casco = fabrica.producto(stock=1)

    with pytest.raises(StockInsuficiente, match="quedan 1"):
        _comprar(sesion, cliente, [(modelo, 1)], [(casco, 2)])

    assert casco.stock == 1
    assert unidad.estado == EstadoVehiculo.DISPONIBLE
    assert not sesion.scalars(select(Venta)).all()


def test_no_vende_una_unidad_con_un_alquiler_futuro(sesion, fabrica, modelo, cliente) -> None:
    con_alquiler = fabrica.vehiculo(modelo)
    libre = fabrica.vehiculo(modelo)
    fabrica.alquiler(con_alquiler, HOY + timedelta(days=10), HOY + timedelta(days=12))

    venta = _comprar(sesion, cliente, [(modelo, 1)])

    assert [i.vehiculo_id for i in venta.items] == [libre.id]
    with pytest.raises(SinUnidadesParaVenta, match="hay 0"):
        _comprar(sesion, cliente, [(modelo, 1)])


def test_un_alquiler_pendiente_vencido_no_impide_vender(sesion, fabrica, modelo, cliente) -> None:
    unidad = fabrica.vehiculo(modelo)
    abandonado = fabrica.alquiler(
        unidad,
        HOY + timedelta(days=3),
        HOY + timedelta(days=4),
        EstadoAlquiler.PENDIENTE_PAGO,
        expira_en=MOMENTO - timedelta(minutes=1),
    )

    _comprar(sesion, cliente, [(modelo, 1)])

    assert abandonado.estado == EstadoAlquiler.EXPIRADO


@pytest.mark.parametrize(
    "estado",
    [EstadoVehiculo.ALQUILADO, EstadoVehiculo.MANTENIMIENTO, EstadoVehiculo.RESERVADO],
)
def test_solo_vende_unidades_disponibles(sesion, fabrica, modelo, cliente, estado) -> None:
    fabrica.vehiculo(modelo, estado)
    with pytest.raises(SinUnidadesParaVenta):
        _comprar(sesion, cliente, [(modelo, 1)])


def test_modelo_solo_de_alquiler_no_se_vende(sesion, fabrica, cliente) -> None:
    modelo = fabrica.modelo(tarifa_diaria=40_000, precio_venta=None)
    fabrica.vehiculo(modelo)
    with pytest.raises(ModeloNoSeVende):
        _comprar(sesion, cliente, [(modelo, 1)])


def test_producto_inactivo_no_se_vende(sesion, fabrica, cliente) -> None:
    descontinuado = fabrica.producto(activo=False)
    with pytest.raises(ProductoNoEncontrado):
        _comprar(sesion, cliente, productos=[(descontinuado, 1)])


def test_solo_un_cliente_compra(sesion, fabrica, operador) -> None:
    casco = fabrica.producto()
    with pytest.raises(PermisoDenegado):
        _comprar(sesion, operador, productos=[(casco, 1)])


def test_una_compra_vencida_se_expira_antes_de_comprar_y_devuelve_todo(
    sesion, fabrica, modelo, cliente, crear_usuario
) -> None:
    unidad = fabrica.vehiculo(modelo)
    casco = fabrica.producto(stock=1)
    abandonada = _comprar(sesion, cliente, [(modelo, 1)], [(casco, 1)])
    assert casco.stock == 0

    despues = MOMENTO + timedelta(minutes=16)
    otra = _comprar(sesion, crear_usuario(Rol.CLIENTE), [(modelo, 1)], [(casco, 1)], despues)

    assert abandonada.estado == EstadoVenta.EXPIRADA
    assert [i.vehiculo_id for i in otra.items if i.vehiculo_id] == [unidad.id]
    assert casco.stock == 0  # volvió a 1 al expirar y la nueva compra lo tomó
    registro = sesion.scalars(
        select(RegistroAuditoria)
        .where(
            RegistroAuditoria.entidad == "ventas",
            RegistroAuditoria.entidad_id == str(abandonada.id),
        )
        .order_by(RegistroAuditoria.id.desc())
    ).first()
    assert registro.usuario_id is None
    assert registro.datos_nuevos["estado"] == "expirada"


# --- Interacción con alquileres (HU-03) --------------------------------------------------


def test_una_unidad_apartada_para_compra_no_se_alquila(sesion, fabrica, modelo, cliente) -> None:
    fabrica.vehiculo(modelo)
    _comprar(sesion, cliente, [(modelo, 1)])

    with pytest.raises(SinUnidadesDisponibles):
        alquileres.crear_alquiler(
            sesion,
            cliente,
            modelo.id,
            HOY + timedelta(days=1),
            HOY + timedelta(days=2),
            hoy=HOY,
            momento=MOMENTO,
        )


def test_reservar_un_alquiler_expira_la_compra_vencida_que_apartaba_la_unidad(
    sesion, fabrica, modelo, cliente
) -> None:
    unidad = fabrica.vehiculo(modelo)
    casco = fabrica.producto(stock=1)
    abandonada = _comprar(sesion, cliente, [(modelo, 1)], [(casco, 1)])

    alquiler = alquileres.crear_alquiler(
        sesion,
        cliente,
        modelo.id,
        HOY + timedelta(days=1),
        HOY + timedelta(days=2),
        hoy=HOY,
        momento=MOMENTO + timedelta(minutes=16),
    )

    assert alquiler.vehiculo_id == unidad.id
    assert abandonada.estado == EstadoVenta.EXPIRADA
    assert unidad.estado == EstadoVehiculo.DISPONIBLE
    assert casco.stock == 1  # la compra expirada también devolvió el producto


# --- Pagar ------------------------------------------------------------------------------


def test_pago_aprobado_completa_la_venta_y_las_unidades_quedan_vendidas(
    sesion, fabrica, modelo, cliente
) -> None:
    unidad = fabrica.vehiculo(modelo)
    venta = _comprar(sesion, cliente, [(modelo, 1)])

    resultado = _pagar(sesion, venta, cliente)

    assert resultado.pago.estado == EstadoPago.APROBADO
    assert resultado.pago.venta_id == venta.id
    assert resultado.devolucion is None
    assert venta.estado == EstadoVenta.PAGADA
    assert venta.expira_en is None
    assert unidad.estado == EstadoVehiculo.VENDIDO


def test_pago_rechazado_deja_la_compra_pendiente(sesion, fabrica, cliente) -> None:
    casco = fabrica.producto(stock=3)
    venta = _comprar(sesion, cliente, productos=[(casco, 1)])

    assert _pagar(sesion, venta, cliente, aprueba=False).pago.estado == EstadoPago.RECHAZADO
    assert venta.estado == EstadoVenta.PENDIENTE_PAGO
    assert casco.stock == 2  # sigue apartado mientras puede reintentar


def test_pagar_tarde_expira_la_compra_y_devuelve_lo_apartado(
    sesion, fabrica, modelo, cliente
) -> None:
    unidad = fabrica.vehiculo(modelo)
    casco = fabrica.producto(stock=1)
    venta = _comprar(sesion, cliente, [(modelo, 1)], [(casco, 1)])

    with pytest.raises(VentaExpirada):
        _pagar(sesion, venta, cliente, momento=MOMENTO + timedelta(minutes=15))

    assert venta.estado == EstadoVenta.EXPIRADA
    assert unidad.estado == EstadoVehiculo.DISPONIBLE
    assert casco.stock == 1
    assert not sesion.scalars(select(Pago).where(Pago.venta_id == venta.id)).all()


def test_una_venta_pagada_no_se_cobra_dos_veces(sesion, fabrica, cliente) -> None:
    venta = _comprar(sesion, cliente, productos=[(fabrica.producto(), 1)])
    _pagar(sesion, venta, cliente)
    with pytest.raises(TransicionDeVentaInvalida):
        _pagar(sesion, venta, cliente)


def test_decision_2_unidad_en_mantenimiento_antes_del_pago_se_devuelve_el_dinero(
    sesion, fabrica, modelo, cliente, operador, crear_usuario
) -> None:
    rota, sana = fabrica.vehiculo(modelo), fabrica.vehiculo(modelo)
    casco = fabrica.producto(stock=2)
    venta = _comprar(sesion, cliente, [(modelo, 2)], [(casco, 1)])
    inventario.inactivar_vehiculo(sesion, rota.id, "Se rompió el manubrio en bodega.", operador)

    resultado = _pagar(sesion, venta, cliente)

    # El cobro se aprobó y no se toca; la devolución es otro registro que lo referencia.
    assert resultado.pago.estado == EstadoPago.APROBADO
    devolucion = resultado.devolucion
    assert devolucion.tipo == TipoPago.COMPENSACION
    assert devolucion.pago_compensado_id == resultado.pago.id
    assert (devolucion.monto, devolucion.estado) == (venta.total, EstadoPago.PENDIENTE)
    # La compra no se completa y todo lo apartado vuelve.
    assert venta.estado == EstadoVenta.CANCELADA
    assert rota.codigo in venta.motivo_cancelacion
    assert rota.estado == EstadoVehiculo.MANTENIMIENTO
    assert sana.estado == EstadoVehiculo.DISPONIBLE
    assert casco.stock == 2
    # Aviso al administrador.
    pendientes = servicio.listar_devoluciones_pendientes(sesion, ParametrosPagina())
    assert [v.id for v in pendientes.elementos] == [venta.id]


# --- Cancelar ---------------------------------------------------------------------------


def test_el_cliente_cancela_una_compra_pendiente_y_todo_vuelve(
    sesion, fabrica, modelo, cliente
) -> None:
    unidad = fabrica.vehiculo(modelo)
    casco = fabrica.producto(stock=1)
    venta = _comprar(sesion, cliente, [(modelo, 1)], [(casco, 1)])

    servicio.cancelar_venta(sesion, venta.id, cliente, "Me equivoqué.", momento=MOMENTO)

    assert venta.estado == EstadoVenta.CANCELADA
    assert venta.motivo_cancelacion == "Me equivoqué."
    assert unidad.estado == EstadoVehiculo.DISPONIBLE
    assert casco.stock == 1


def test_una_compra_pagada_no_se_cancela(sesion, fabrica, cliente) -> None:
    venta = _comprar(sesion, cliente, productos=[(fabrica.producto(), 1)])
    _pagar(sesion, venta, cliente)
    with pytest.raises(VentaNoCancelable):
        servicio.cancelar_venta(sesion, venta.id, cliente, momento=MOMENTO)


def test_otro_cliente_no_ve_ni_paga_la_compra(sesion, fabrica, cliente, crear_usuario) -> None:
    venta = _comprar(sesion, cliente, productos=[(fabrica.producto(), 1)])
    intruso = crear_usuario(Rol.CLIENTE)
    with pytest.raises(VentaNoEncontrada):
        _pagar(sesion, venta, intruso)
    with pytest.raises(VentaNoEncontrada):
        servicio.obtener_venta(sesion, venta.id, intruso)


# --- Inventario: una unidad apartada no vuelve a servicio ---------------------------------


def test_unidad_apartada_por_una_compra_vigente_no_vuelve_a_servicio(
    sesion, fabrica, modelo, cliente, operador
) -> None:
    unidad = fabrica.vehiculo(modelo)
    _comprar(sesion, cliente, [(modelo, 1)], momento=datetime.now(UTC))
    operacion = inventario.inactivar_vehiculo(sesion, unidad.id, "Revisión rápida.", operador)
    novedad: NovedadVehiculo = operacion.novedad

    with pytest.raises(NoPuedeVolverAServicio, match="compra pendiente"):
        inventario.cerrar_novedad(
            sesion,
            unidad.id,
            novedad.id,
            CierreNovedad(solucion="Todo en orden.", devolver_a_servicio=True),
            operador,
        )


# --- Comprobante preliminar y listados ---------------------------------------------------


def test_comprobante_trae_cliente_items_total_y_pago(sesion, fabrica, modelo, cliente) -> None:
    fabrica.vehiculo(modelo)
    venta = _comprar(sesion, cliente, [(modelo, 1)])
    _pagar(sesion, venta, cliente, aprueba=False)
    _pagar(sesion, venta, cliente)

    datos = servicio.obtener_comprobante(sesion, venta.id, cliente)

    assert datos.venta.cliente.id == cliente.id
    assert datos.pago.estado == EstadoPago.APROBADO  # el aprobado, no el último rechazado
    assert datos.metodo == "Tarjeta de crédito o débito"


def test_comprobante_sin_pago(sesion, fabrica, cliente) -> None:
    venta = _comprar(sesion, cliente, productos=[(fabrica.producto(), 1)])
    datos = servicio.obtener_comprobante(sesion, venta.id, cliente)
    assert (datos.pago, datos.metodo) == (None, None)


def test_mis_compras_y_filtro_de_vencidas(sesion, fabrica, cliente, crear_usuario) -> None:
    casco = fabrica.producto(stock=10)
    vencida = _comprar(sesion, cliente, productos=[(casco, 1)])
    _comprar(sesion, crear_usuario(Rol.CLIENTE), productos=[(casco, 1)])

    mias = servicio.listar_ventas(sesion, ParametrosPagina(), cliente_id=cliente.id)
    expiradas = servicio.listar_ventas(
        sesion,
        ParametrosPagina(),
        cliente_id=cliente.id,
        estado=EstadoVenta.EXPIRADA,
        momento=MOMENTO + timedelta(hours=1),
    )

    assert [v.id for v in mias.elementos] == [vencida.id]
    assert [v.id for v in expiradas.elementos] == [vencida.id]


def test_listado_de_productos(sesion, fabrica) -> None:
    casco = fabrica.producto(nombre="Casco", stock=3)
    fabrica.producto(nombre="Cadena", stock=0, categoria=CategoriaProducto.REPUESTO)
    fabrica.producto(nombre="Descontinuado", activo=False)

    def _nombres(**filtros):
        pagina = inventario.listar_productos(sesion, ParametrosPagina(), **filtros)
        return [p.nombre for p in pagina.elementos]

    assert _nombres() == ["Cadena", "Casco"]
    assert _nombres(categoria=CategoriaProducto.REPUESTO) == ["Cadena"]
    assert _nombres(solo_disponibles=True) == [casco.nombre]
