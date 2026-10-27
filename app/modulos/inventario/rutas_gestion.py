"""Rutas de la gestión del inventario (HU-10): ``/inventario``.

Consultar (listas, alertas, resumen): administrador y operador. Crear, editar y ajustar:
solo el administrador. La lista de la flota con su estado sigue en ``GET /vehiculos``.
"""

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.comun.errores import respuestas_error
from app.comun.paginacion import Pagina, Paginacion
from app.db import SesionBD
from app.modulos.inventario import gestion
from app.modulos.inventario.esquemas import VehiculoGestion
from app.modulos.inventario.esquemas_gestion import (
    AjusteStock,
    ModeloActualizar,
    ModeloCrear,
    ModeloGestion,
    ProductoActualizar,
    ProductoCrear,
    ProductoGestion,
    ResumenInventario,
    TipoVehiculoActualizar,
    TipoVehiculoCrear,
    TipoVehiculoGestion,
    UnidadActualizar,
    UnidadCrear,
)
from app.modulos.inventario.modelos import CategoriaProducto
from app.seguridad import AdministradorUOperador, SoloAdministrador

enrutador_inventario = APIRouter(prefix="/inventario", tags=["inventario"])

_LECTURA = respuestas_error(401, 403, 422)
_CREAR = respuestas_error(401, 403, 404, 409, 422)
_EDITAR = respuestas_error(401, 403, 404, 409, 422)


# --- Resumen y alertas ------------------------------------------------------------------------


@enrutador_inventario.get(
    "/resumen",
    response_model=ResumenInventario,
    summary="Resumen del inventario",
    responses=_LECTURA,
)
def resumen(sesion: SesionBD, usuario: AdministradorUOperador) -> ResumenInventario:
    """Unidades por estado y cuántos productos están en alerta de stock."""
    return ResumenInventario.model_validate(gestion.resumen(sesion, usuario))


@enrutador_inventario.get(
    "/alertas-stock",
    response_model=Pagina[ProductoGestion],
    summary="Alertas de bajo stock",
    responses=_LECTURA,
)
def alertas_stock(
    sesion: SesionBD, usuario: AdministradorUOperador, parametros: Paginacion
) -> Pagina[ProductoGestion]:
    """Productos activos en o bajo su `stock_minimo`, los más urgentes primero. No se envía
    correo ni SMS: el frontend consulta esta lista.
    """
    return Pagina[ProductoGestion].model_validate(
        gestion.alertas_de_stock(sesion, parametros, usuario)
    )


# --- Tipos de vehículo ------------------------------------------------------------------------


@enrutador_inventario.get(
    "/tipos",
    response_model=Pagina[TipoVehiculoGestion],
    summary="Tipos de vehículo",
    responses=_LECTURA,
)
def listar_tipos(
    sesion: SesionBD, usuario: AdministradorUOperador, parametros: Paginacion
) -> Pagina[TipoVehiculoGestion]:
    """Todos, activos o no."""
    return Pagina[TipoVehiculoGestion].model_validate(
        gestion.listar_tipos(sesion, parametros, usuario)
    )


@enrutador_inventario.post(
    "/tipos",
    response_model=TipoVehiculoGestion,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un tipo de vehículo",
    responses=_CREAR,
)
def crear_tipo(
    sesion: SesionBD, usuario: SoloAdministrador, datos: TipoVehiculoCrear
) -> TipoVehiculoGestion:
    return TipoVehiculoGestion.model_validate(gestion.crear_tipo(sesion, datos, usuario))


@enrutador_inventario.patch(
    "/tipos/{tipo_id}",
    response_model=TipoVehiculoGestion,
    summary="Editar un tipo de vehículo",
    responses=_EDITAR,
)
def actualizar_tipo(
    sesion: SesionBD, usuario: SoloAdministrador, tipo_id: int, datos: TipoVehiculoActualizar
) -> TipoVehiculoGestion:
    """`{"activo": false}` lo oculta del catálogo, con todos sus modelos."""
    return TipoVehiculoGestion.model_validate(
        gestion.actualizar_tipo(sesion, tipo_id, datos, usuario)
    )


# --- Modelos --------------------------------------------------------------------------------


@enrutador_inventario.get(
    "/modelos", response_model=Pagina[ModeloGestion], summary="Modelos", responses=_LECTURA
)
def listar_modelos(
    sesion: SesionBD,
    usuario: AdministradorUOperador,
    parametros: Paginacion,
    tipo_id: Annotated[int | None, Query(gt=0)] = None,
    activo: bool | None = None,
) -> Pagina[ModeloGestion]:
    """Todos los modelos con sus tarifas, activos o no."""
    resultado = gestion.listar_modelos(sesion, parametros, usuario, tipo_id=tipo_id, activo=activo)
    return Pagina[ModeloGestion].model_validate(resultado)


@enrutador_inventario.post(
    "/modelos",
    response_model=ModeloGestion,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un modelo",
    responses=_CREAR,
)
def crear_modelo(sesion: SesionBD, usuario: SoloAdministrador, datos: ModeloCrear) -> ModeloGestion:
    """Con `tarifa_diaria` se alquila; con `precio_venta` se vende; puede tener ambos."""
    return ModeloGestion.model_validate(gestion.crear_modelo(sesion, datos, usuario))


@enrutador_inventario.patch(
    "/modelos/{modelo_id}",
    response_model=ModeloGestion,
    summary="Editar un modelo (tarifas, precio, ficha)",
    responses=_EDITAR,
)
def actualizar_modelo(
    sesion: SesionBD, usuario: SoloAdministrador, modelo_id: int, datos: ModeloActualizar
) -> ModeloGestion:
    """El cambio de tarifa o precio aplica a operaciones nuevas; las hechas conservan el suyo."""
    return ModeloGestion.model_validate(
        gestion.actualizar_modelo(sesion, modelo_id, datos, usuario)
    )


# --- Unidades -------------------------------------------------------------------------------


@enrutador_inventario.post(
    "/unidades",
    response_model=VehiculoGestion,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una unidad",
    responses=_CREAR,
)
def crear_unidad(
    sesion: SesionBD, usuario: SoloAdministrador, datos: UnidadCrear
) -> VehiculoGestion:
    """Entra `disponible`. El código se guarda en mayúsculas."""
    return VehiculoGestion.model_validate(gestion.crear_unidad(sesion, datos, usuario))


@enrutador_inventario.patch(
    "/unidades/{vehiculo_id}",
    response_model=VehiculoGestion,
    summary="Editar una unidad (batería, ubicación, observaciones)",
    responses=_EDITAR,
)
def actualizar_unidad(
    sesion: SesionBD, usuario: SoloAdministrador, vehiculo_id: int, datos: UnidadActualizar
) -> VehiculoGestion:
    """El estado no se cambia aquí: tiene sus propios flujos (alquiler, venta, mantenimiento)."""
    return VehiculoGestion.model_validate(
        gestion.actualizar_unidad(sesion, vehiculo_id, datos, usuario)
    )


# --- Productos ------------------------------------------------------------------------------


@enrutador_inventario.get(
    "/productos", response_model=Pagina[ProductoGestion], summary="Productos", responses=_LECTURA
)
def listar_productos(
    sesion: SesionBD,
    usuario: AdministradorUOperador,
    parametros: Paginacion,
    categoria: CategoriaProducto | None = None,
    activo: bool | None = None,
    solo_bajo_stock: bool = False,
) -> Pagina[ProductoGestion]:
    """Todos, activos o no, con su stock y su mínimo."""
    resultado = gestion.listar_productos(
        sesion,
        parametros,
        usuario,
        categoria=categoria,
        activo=activo,
        solo_bajo_stock=solo_bajo_stock,
    )
    return Pagina[ProductoGestion].model_validate(resultado)


@enrutador_inventario.post(
    "/productos",
    response_model=ProductoGestion,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un producto",
    responses=_CREAR,
)
def crear_producto(
    sesion: SesionBD, usuario: SoloAdministrador, datos: ProductoCrear
) -> ProductoGestion:
    return ProductoGestion.model_validate(gestion.crear_producto(sesion, datos, usuario))


@enrutador_inventario.patch(
    "/productos/{producto_id}",
    response_model=ProductoGestion,
    summary="Editar un producto",
    responses=_EDITAR,
)
def actualizar_producto(
    sesion: SesionBD, usuario: SoloAdministrador, producto_id: int, datos: ProductoActualizar
) -> ProductoGestion:
    """El stock no se edita aquí: usa el ajuste de stock."""
    return ProductoGestion.model_validate(
        gestion.actualizar_producto(sesion, producto_id, datos, usuario)
    )


@enrutador_inventario.post(
    "/productos/{producto_id}/ajustes",
    response_model=ProductoGestion,
    summary="Ajustar el stock (entrada o salida)",
    responses=_EDITAR,
)
def ajustar_stock(
    sesion: SesionBD, usuario: SoloAdministrador, producto_id: int, datos: AjusteStock
) -> ProductoGestion:
    """`cantidad` positiva (llegó mercancía) o negativa (daño, pérdida), con `motivo`. Queda
    en auditoría. Nunca deja el stock en negativo.
    """
    return ProductoGestion.model_validate(
        gestion.ajustar_stock(sesion, producto_id, datos, usuario)
    )
