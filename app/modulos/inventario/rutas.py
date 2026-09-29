"""Rutas del catálogo público (HU-02). No requieren iniciar sesión."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.comun.errores import respuestas_error
from app.comun.paginacion import Pagina, Paginacion
from app.db import SesionBD
from app.modulos.inventario import servicio
from app.modulos.inventario.esquemas import (
    DisponibilidadRango,
    FiltrosDelCatalogo,
    ModeloCatalogo,
    ModeloDetalle,
    TipoVehiculoRespuesta,
)

enrutador_catalogo = APIRouter(prefix="/catalogo", tags=["catálogo"])


@enrutador_catalogo.get(
    "/tipos",
    response_model=Pagina[TipoVehiculoRespuesta],
    summary="Tipos de vehículo",
    responses=respuestas_error(422),
)
def listar_tipos(sesion: SesionBD, parametros: Paginacion) -> Pagina[TipoVehiculoRespuesta]:
    """Tipos activos (cicla, patín, monopatín eléctrico...), para armar el filtro."""
    return Pagina[TipoVehiculoRespuesta].model_validate(servicio.listar_tipos(sesion, parametros))


@enrutador_catalogo.get(
    "/modelos",
    response_model=Pagina[ModeloCatalogo],
    summary="Catálogo de vehículos",
    responses=respuestas_error(422),
)
def listar_modelos(
    sesion: SesionBD, parametros: Paginacion, filtros: FiltrosDelCatalogo
) -> Pagina[ModeloCatalogo]:
    """Modelos del catálogo con sus unidades disponibles hoy. Filtros combinables."""
    resultado = servicio.listar_modelos(sesion, parametros, filtros)
    return Pagina[ModeloCatalogo](
        elementos=[ModeloCatalogo.desde(e.modelo, e.disponibles_hoy) for e in resultado.elementos],
        total=resultado.total,
        pagina=resultado.pagina,
        tamano=resultado.tamano,
        paginas=resultado.paginas,
    )


@enrutador_catalogo.get(
    "/modelos/{modelo_id}",
    response_model=ModeloDetalle,
    summary="Detalle de un modelo",
    responses=respuestas_error(404),
)
def ver_modelo(sesion: SesionBD, modelo_id: int) -> ModeloDetalle:
    """Ficha del modelo con cada unidad libre hoy: código, ubicación y batería."""
    resultado = servicio.obtener_modelo(sesion, modelo_id)
    return ModeloDetalle.desde_unidades(resultado.modelo, resultado.unidades)


@enrutador_catalogo.get(
    "/modelos/{modelo_id}/disponibilidad",
    response_model=DisponibilidadRango,
    summary="Disponibilidad para un rango de fechas",
    responses=respuestas_error(404, 409, 422),
)
def consultar_disponibilidad(
    sesion: SesionBD,
    modelo_id: int,
    fecha_inicio: Annotated[date, Query(description="Primer día del alquiler (AAAA-MM-DD).")],
    fecha_fin: Annotated[date, Query(description="Último día del alquiler, inclusive.")],
) -> DisponibilidadRango:
    """Unidades libres durante todo el rango. Del 5 al 7 son 3 días (fechas inclusivas)."""
    resultado = servicio.consultar_disponibilidad(sesion, modelo_id, fecha_inicio, fecha_fin)
    return DisponibilidadRango.model_validate(resultado)
