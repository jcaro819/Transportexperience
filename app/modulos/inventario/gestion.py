"""Gestión del inventario por el administrador (HU-10, SRS 3.1.4 y 3.5.4).

Crear y editar tipos de vehículo, modelos, unidades y productos; ajustar el stock; y las
alertas de bajo stock. Todo cambio queda en auditoría con el antes y el después (las
tarifas y los precios incluidos, SRS 3.5.4).

Leer (listas, alertas, resumen) lo pueden el administrador y el operador; cambiar, solo el
administrador. Las alertas son una consulta: no se envía correo ni SMS (HU-14 está fuera
del MVP).

Vive aparte de ``servicio.py`` (catálogo y flota) para no mezclar la administración del
inventario con su operación diaria.
"""

from enum import StrEnum
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.auditoria import registrar_auditoria
from app.comun.errores import PermisoDenegado
from app.comun.paginacion import ParametrosPagina, ResultadoPagina, paginar
from app.modulos.inventario.esquemas_gestion import (
    AjusteStock,
    ModeloActualizar,
    ModeloCrear,
    ProductoActualizar,
    ProductoCrear,
    TipoVehiculoActualizar,
    TipoVehiculoCrear,
    UnidadActualizar,
    UnidadCrear,
)
from app.modulos.inventario.excepciones import (
    AjusteDeStockInvalido,
    BateriaNoAplica,
    CodigoDuplicado,
    ModeloNoEncontrado,
    ModeloSinPrecio,
    NombreDuplicado,
    TipoNoEncontrado,
    VehiculoVendido,
)
from app.modulos.inventario.modelos import (
    CategoriaProducto,
    EstadoVehiculo,
    ModeloVehiculo,
    Producto,
    TipoVehiculo,
    Vehiculo,
)
from app.modulos.inventario.servicio import ROLES_DE_TALLER, bloquear_vehiculo
from app.modulos.usuarios.modelos import Rol, Usuario
from app.modulos.ventas.excepciones import ProductoNoEncontrado


def _solo_administrador(usuario: Usuario) -> None:
    if usuario.rol != Rol.ADMINISTRADOR:
        raise PermisoDenegado()


def _solo_taller(usuario: Usuario) -> None:
    if usuario.rol not in ROLES_DE_TALLER:
        raise PermisoDenegado()


def _json(valor: Any) -> Any:
    return valor.value if isinstance(valor, StrEnum) else valor


def _auditar(sesion, usuario, accion, entidad, entidad_id, antes=None, despues=None) -> None:
    registrar_auditoria(
        sesion,
        usuario_id=usuario.id,
        accion=accion,
        entidad=entidad,
        entidad_id=entidad_id,
        antes={k: _json(v) for k, v in antes.items()} if antes is not None else None,
        despues={k: _json(v) for k, v in despues.items()} if despues is not None else None,
    )


def _aplicar(registro: Any, cambios: dict[str, Any]) -> tuple[dict, dict]:
    """Aplica los cambios y devuelve el antes y el después, solo de lo que cambió."""
    antes, despues = {}, {}
    for campo, valor in cambios.items():
        if getattr(registro, campo) != valor:
            antes[campo], despues[campo] = getattr(registro, campo), valor
            setattr(registro, campo, valor)
    return antes, despues


def _guardar(sesion: Session, registro: Any, duplicado: type[Exception]) -> None:
    """``flush`` dentro de un SAVEPOINT: si choca con un único, lanza ``duplicado``.

    Hay una verificación previa con mensaje claro; esto cubre la carrera entre dos
    administradores creando lo mismo al mismo tiempo.
    """
    try:
        with sesion.begin_nested():
            sesion.add(registro)
            sesion.flush()
    except IntegrityError as error:
        if "uq_" in str(error.orig):
            raise duplicado() from error
        raise


# --- Tipos de vehículo ----------------------------------------------------------------------


def listar_tipos(
    sesion: Session, parametros: ParametrosPagina, usuario: Usuario
) -> ResultadoPagina:
    """Todos los tipos, activos o no (el catálogo público solo muestra los activos)."""
    _solo_taller(usuario)
    return paginar(sesion, select(TipoVehiculo).order_by(TipoVehiculo.nombre), parametros)


def _tipo(sesion: Session, tipo_id: int) -> TipoVehiculo:
    tipo = sesion.get(TipoVehiculo, tipo_id)
    if tipo is None:
        raise TipoNoEncontrado()
    return tipo


def _nombre_de_tipo_libre(sesion: Session, nombre: str, excepto: int | None = None) -> None:
    consulta = select(TipoVehiculo.id).where(func.lower(TipoVehiculo.nombre) == nombre.lower())
    if excepto is not None:
        consulta = consulta.where(TipoVehiculo.id != excepto)
    if sesion.scalar(consulta) is not None:
        raise NombreDuplicado(f"Ya existe el tipo de vehículo «{nombre}».")


def crear_tipo(sesion: Session, datos: TipoVehiculoCrear, usuario: Usuario) -> TipoVehiculo:
    _solo_administrador(usuario)
    _nombre_de_tipo_libre(sesion, datos.nombre)
    tipo = TipoVehiculo(nombre=datos.nombre, usa_bateria=datos.usa_bateria)
    _guardar(sesion, tipo, NombreDuplicado)
    _auditar(sesion, usuario, "crear", "tipos_vehiculo", tipo.id, despues=datos.model_dump())
    sesion.commit()
    return tipo


def actualizar_tipo(
    sesion: Session, tipo_id: int, datos: TipoVehiculoActualizar, usuario: Usuario
) -> TipoVehiculo:
    _solo_administrador(usuario)
    tipo = _tipo(sesion, tipo_id)
    cambios = datos.model_dump(exclude_unset=True)
    if "nombre" in cambios:
        _nombre_de_tipo_libre(sesion, cambios["nombre"], excepto=tipo.id)
    antes, despues = _aplicar(tipo, cambios)
    if despues:
        _guardar(sesion, tipo, NombreDuplicado)
        _auditar(sesion, usuario, "actualizar", "tipos_vehiculo", tipo.id, antes, despues)
    sesion.commit()
    return tipo


# --- Modelos --------------------------------------------------------------------------------


def listar_modelos(
    sesion: Session,
    parametros: ParametrosPagina,
    usuario: Usuario,
    *,
    tipo_id: int | None = None,
    activo: bool | None = None,
) -> ResultadoPagina:
    """Todos los modelos con sus tarifas, activos o no."""
    _solo_taller(usuario)
    consulta = (
        select(ModeloVehiculo)
        .options(joinedload(ModeloVehiculo.tipo))
        .order_by(ModeloVehiculo.nombre, ModeloVehiculo.id)
    )
    if tipo_id is not None:
        consulta = consulta.where(ModeloVehiculo.tipo_vehiculo_id == tipo_id)
    if activo is not None:
        consulta = consulta.where(ModeloVehiculo.activo == activo)
    return paginar(sesion, consulta, parametros)


def _modelo(sesion: Session, modelo_id: int) -> ModeloVehiculo:
    modelo = sesion.get(ModeloVehiculo, modelo_id)
    if modelo is None:
        raise ModeloNoEncontrado("No existe ese modelo.")
    return modelo


def crear_modelo(sesion: Session, datos: ModeloCrear, usuario: Usuario) -> ModeloVehiculo:
    _solo_administrador(usuario)
    _tipo(sesion, datos.tipo_vehiculo_id)
    modelo = ModeloVehiculo(**datos.model_dump())
    _guardar(sesion, modelo, NombreDuplicado)
    _auditar(sesion, usuario, "crear", "modelos_vehiculo", modelo.id, despues=datos.model_dump())
    sesion.commit()
    return modelo


def actualizar_modelo(
    sesion: Session, modelo_id: int, datos: ModeloActualizar, usuario: Usuario
) -> ModeloVehiculo:
    """Cambiar la tarifa o el precio no altera alquileres ni ventas ya hechos (guardan copia)."""
    _solo_administrador(usuario)
    modelo = _modelo(sesion, modelo_id)
    cambios = datos.model_dump(exclude_unset=True)
    if "tipo_vehiculo_id" in cambios:
        _tipo(sesion, cambios["tipo_vehiculo_id"])
    tarifa = cambios.get("tarifa_diaria", modelo.tarifa_diaria)
    precio = cambios.get("precio_venta", modelo.precio_venta)
    if tarifa is None and precio is None:
        # La base también lo impide (ck_modelos_vehiculo_alquila_o_vende); aquí, con mensaje.
        raise ModeloSinPrecio()
    antes, despues = _aplicar(modelo, cambios)
    if despues:
        _auditar(sesion, usuario, "actualizar", "modelos_vehiculo", modelo.id, antes, despues)
    sesion.commit()
    sesion.refresh(modelo)
    return modelo


# --- Unidades -------------------------------------------------------------------------------


def _validar_bateria(modelo: ModeloVehiculo, nivel: int | None) -> None:
    if nivel is not None and not modelo.tipo.usa_bateria:
        raise BateriaNoAplica(f"Un(a) {modelo.tipo.nombre.lower()} no usa batería.")


def _codigo_libre(sesion: Session, entidad: type, codigo: str) -> None:
    if sesion.scalar(select(entidad.id).where(entidad.codigo == codigo)) is not None:
        raise CodigoDuplicado(f"Ya existe el código {codigo}.")


def crear_unidad(sesion: Session, datos: UnidadCrear, usuario: Usuario) -> Vehiculo:
    """Una unidad nueva entra ``disponible`` y aparece en el catálogo si su modelo está activo."""
    _solo_administrador(usuario)
    modelo = _modelo(sesion, datos.modelo_id)
    _validar_bateria(modelo, datos.nivel_bateria)
    _codigo_libre(sesion, Vehiculo, datos.codigo)
    vehiculo = Vehiculo(**datos.model_dump(), estado=EstadoVehiculo.DISPONIBLE)
    _guardar(sesion, vehiculo, CodigoDuplicado)
    _auditar(sesion, usuario, "crear", "vehiculos", vehiculo.id, despues=datos.model_dump())
    sesion.commit()
    sesion.refresh(vehiculo)
    return vehiculo


def actualizar_unidad(
    sesion: Session, vehiculo_id: int, datos: UnidadActualizar, usuario: Usuario
) -> Vehiculo:
    """Batería, ubicación y observaciones. La fila se bloquea como en toda operación (7.1)."""
    _solo_administrador(usuario)
    vehiculo = bloquear_vehiculo(sesion, vehiculo_id)
    if vehiculo.estado == EstadoVehiculo.VENDIDO:
        raise VehiculoVendido()
    cambios = datos.model_dump(exclude_unset=True)
    if "nivel_bateria" in cambios:
        _validar_bateria(vehiculo.modelo, cambios["nivel_bateria"])
    antes, despues = _aplicar(vehiculo, cambios)
    if despues:
        _auditar(sesion, usuario, "actualizar", "vehiculos", vehiculo.id, antes, despues)
    sesion.commit()
    return vehiculo


# --- Productos y stock ----------------------------------------------------------------------


def listar_productos(
    sesion: Session,
    parametros: ParametrosPagina,
    usuario: Usuario,
    *,
    categoria: CategoriaProducto | None = None,
    activo: bool | None = None,
    solo_bajo_stock: bool = False,
) -> ResultadoPagina:
    """Todos los productos, activos o no, con su stock y su mínimo."""
    _solo_taller(usuario)
    consulta = select(Producto).order_by(Producto.nombre, Producto.id)
    if categoria is not None:
        consulta = consulta.where(Producto.categoria == categoria)
    if activo is not None:
        consulta = consulta.where(Producto.activo == activo)
    if solo_bajo_stock:
        consulta = consulta.where(Producto.stock <= Producto.stock_minimo)
    return paginar(sesion, consulta, parametros)


def alertas_de_stock(
    sesion: Session, parametros: ParametrosPagina, usuario: Usuario
) -> ResultadoPagina:
    """HU-10: productos activos en o bajo su stock mínimo, los más urgentes primero."""
    _solo_taller(usuario)
    consulta = (
        select(Producto)
        .where(Producto.activo, Producto.stock <= Producto.stock_minimo)
        .order_by((Producto.stock - Producto.stock_minimo).asc(), Producto.nombre)
    )
    return paginar(sesion, consulta, parametros)


def _bloquear_producto(sesion: Session, producto_id: int) -> Producto:
    producto = sesion.scalars(
        select(Producto)
        .where(Producto.id == producto_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if producto is None:
        raise ProductoNoEncontrado("No existe ese producto.")
    return producto


def crear_producto(sesion: Session, datos: ProductoCrear, usuario: Usuario) -> Producto:
    _solo_administrador(usuario)
    _codigo_libre(sesion, Producto, datos.codigo)
    producto = Producto(**datos.model_dump())
    _guardar(sesion, producto, CodigoDuplicado)
    _auditar(sesion, usuario, "crear", "productos", producto.id, despues=datos.model_dump())
    sesion.commit()
    return producto


def actualizar_producto(
    sesion: Session, producto_id: int, datos: ProductoActualizar, usuario: Usuario
) -> Producto:
    _solo_administrador(usuario)
    producto = _bloquear_producto(sesion, producto_id)
    antes, despues = _aplicar(producto, datos.model_dump(exclude_unset=True))
    if despues:
        _auditar(sesion, usuario, "actualizar", "productos", producto.id, antes, despues)
    sesion.commit()
    return producto


def ajustar_stock(
    sesion: Session, producto_id: int, datos: AjusteStock, usuario: Usuario
) -> Producto:
    """Suma o resta stock sobre la fila bloqueada (``FOR UPDATE``).

    Se aplica la **diferencia**, no un valor absoluto: si una compra descuenta stock al
    mismo tiempo, las dos operaciones se esperan y ninguna pisa a la otra.
    """
    _solo_administrador(usuario)
    producto = _bloquear_producto(sesion, producto_id)
    nuevo = producto.stock + datos.cantidad
    if nuevo < 0:
        raise AjusteDeStockInvalido(
            f"Hay {producto.stock} y el ajuste saca {-datos.cantidad}: quedaría en {nuevo}."
        )
    anterior = producto.stock
    producto.stock = nuevo
    _auditar(
        sesion,
        usuario,
        "ajustar_stock",
        "productos",
        producto.id,
        {"stock": anterior},
        {"stock": nuevo, "cantidad": datos.cantidad, "motivo": datos.motivo},
    )
    sesion.commit()
    return producto


# --- Resumen --------------------------------------------------------------------------------


def resumen(sesion: Session, usuario: Usuario) -> dict[str, Any]:
    """Unidades por estado y productos en alerta, para el tablero del administrador."""
    _solo_taller(usuario)
    por_estado = dict.fromkeys(EstadoVehiculo, 0)
    for estado, cantidad in sesion.execute(
        select(Vehiculo.estado, func.count()).group_by(Vehiculo.estado)
    ):
        por_estado[estado] = cantidad
    activos = sesion.scalar(select(func.count()).where(Producto.activo)) or 0
    bajo_stock = (
        sesion.scalar(
            select(func.count()).where(Producto.activo, Producto.stock <= Producto.stock_minimo)
        )
        or 0
    )
    return {
        "total_unidades": sum(por_estado.values()),
        "unidades_por_estado": por_estado,
        "productos_activos": activos,
        "productos_bajo_stock": bajo_stock,
    }
