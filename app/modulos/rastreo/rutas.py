"""Rutas del rastreo GPS (HU-08).

- ``POST /rastreo/posiciones``: lo llaman los dispositivos GPS y el simulador, con la clave
  del vehículo en ``X-Clave-Gps`` (no con el JWT de usuarios).
- El resto es del administrador y el operador: el mapa de la flota (consultado cada 5 s),
  el recorrido de una unidad y la emisión de claves.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security, status
from fastapi.security import APIKeyHeader

from app.comun.errores import respuestas_error
from app.comun.paginacion import Pagina, Paginacion
from app.config import obtener_configuracion
from app.db import SesionBD
from app.modulos.inventario.esquemas import ModeloResumen
from app.modulos.inventario.modelos import Vehiculo
from app.modulos.rastreo import servicio
from app.modulos.rastreo.esquemas import (
    ClaveGpsCrear,
    ClaveGpsEmitida,
    PosicionCrear,
    PosicionRecibida,
    PosicionRespuesta,
    Senal,
    VehiculoEnMapa,
)
from app.seguridad import AdministradorUOperador, SoloAdministrador

enrutador_rastreo = APIRouter(prefix="/rastreo", tags=["rastreo GPS"])

# auto_error=False: si falta, respondemos con el error uniforme de la API.
_clave_gps = APIKeyHeader(
    name="X-Clave-Gps",
    auto_error=False,
    description="Clave del vehículo, emitida con `POST /rastreo/vehiculos/{id}/clave`.",
)


def _vehiculo_del_dispositivo(
    sesion: SesionBD, clave: Annotated[str | None, Security(_clave_gps)]
) -> Vehiculo:
    return servicio.vehiculo_por_clave(sesion, clave)


VehiculoDelDispositivo = Annotated[Vehiculo, Depends(_vehiculo_del_dispositivo)]


@enrutador_rastreo.post(
    "/posiciones",
    response_model=PosicionRecibida,
    status_code=status.HTTP_201_CREATED,
    summary="Reportar una posición (dispositivo GPS o simulador)",
    responses=respuestas_error(401, 403, 422),
)
def reportar_posicion(
    sesion: SesionBD, vehiculo: VehiculoDelDispositivo, datos: PosicionCrear
) -> PosicionRecibida:
    """Cada 5 segundos. Se autentica con la clave del vehículo en `X-Clave-Gps`. Las
    coordenadas se guardan con 6 decimales. Solo se aceptan posiciones de la fuente activa
    en el servidor (`GPS_FUENTE`).
    """
    fuente = obtener_configuracion().gps_fuente
    posicion = servicio.registrar_posicion(sesion, vehiculo, datos, fuente)
    return PosicionRecibida(vehiculo_codigo=vehiculo.codigo, registrado_en=posicion.registrado_en)


@enrutador_rastreo.get(
    "/flota",
    response_model=Pagina[VehiculoEnMapa],
    summary="Mapa de la flota",
    responses=respuestas_error(401, 403, 422),
)
def flota(
    sesion: SesionBD,
    _: AdministradorUOperador,
    parametros: Paginacion,
    senal: Annotated[Senal | None, Query(description="Filtra por estado de la señal.")] = None,
) -> Pagina[VehiculoEnMapa]:
    """Última posición de cada vehículo con GPS y si está `en_linea`, `sin_senal` o
    `sin_datos`. Pensado para consultarse cada 5 segundos.
    """
    resultado = servicio.listar_flota(sesion, parametros, senal=senal)
    return Pagina[VehiculoEnMapa](
        elementos=[
            VehiculoEnMapa(
                vehiculo_id=r.vehiculo.id,
                codigo=r.vehiculo.codigo,
                modelo=ModeloResumen.model_validate(r.vehiculo.modelo),
                estado=r.vehiculo.estado,
                senal=r.senal,
                segundos_sin_reportar=r.segundos_sin_reportar,
                posicion=PosicionRespuesta.model_validate(r.posicion) if r.posicion else None,
            )
            for r in resultado.elementos
        ],
        total=resultado.total,
        pagina=resultado.pagina,
        tamano=resultado.tamano,
        paginas=resultado.paginas,
    )


@enrutador_rastreo.get(
    "/vehiculos/{vehiculo_id}/recorrido",
    response_model=Pagina[PosicionRespuesta],
    summary="Recorrido de una unidad",
    responses=respuestas_error(401, 403, 404, 422),
)
def recorrido(
    sesion: SesionBD,
    _: AdministradorUOperador,
    vehiculo_id: int,
    parametros: Paginacion,
    desde: Annotated[datetime | None, Query(description="Por defecto, hace una hora.")] = None,
    hasta: Annotated[datetime | None, Query(description="Por defecto, ahora.")] = None,
) -> Pagina[PosicionRespuesta]:
    """Posiciones en orden cronológico, dentro de los últimos 7 días."""
    resultado = servicio.recorrido(sesion, vehiculo_id, parametros, desde=desde, hasta=hasta)
    return Pagina[PosicionRespuesta].model_validate(resultado)


@enrutador_rastreo.post(
    "/vehiculos/{vehiculo_id}/clave",
    response_model=ClaveGpsEmitida,
    status_code=status.HTTP_201_CREATED,
    summary="Emitir la clave GPS de una unidad",
    responses=respuestas_error(401, 403, 404, 422),
)
def emitir_clave(
    sesion: SesionBD, administrador: SoloAdministrador, vehiculo_id: int, datos: ClaveGpsCrear
) -> ClaveGpsEmitida:
    """La clave se muestra **una sola vez**; en la base queda solo su hash. Emitir otra
    invalida la anterior.
    """
    vehiculo, clave = servicio.emitir_clave(sesion, vehiculo_id, administrador, datos.fuente)
    return ClaveGpsEmitida(
        vehiculo_id=vehiculo.id,
        vehiculo_codigo=vehiculo.codigo,
        fuente=vehiculo.fuente_gps,
        clave=clave,
        emitida_en=vehiculo.clave_gps_emitida_en,
    )
