"""Rutas del portal institucional (HU-01).

Lectura pública, sin login. Edición solo del administrador (SRS 3.5.3).
"""

from fastapi import APIRouter

from app.comun.errores import respuestas_error
from app.db import SesionBD
from app.modulos.portal import servicio
from app.modulos.portal.esquemas import (
    HorarioDia,
    HorarioEditar,
    PortalRespuesta,
    SeccionEditar,
    SeccionRespuesta,
)
from app.modulos.portal.modelos import DiaSemana, SeccionPortal
from app.seguridad import SoloAdministrador

enrutador_portal = APIRouter(prefix="/portal", tags=["portal"])


def _horario(horario: servicio.Horario) -> HorarioDia:
    return HorarioDia(
        dia=horario.dia,
        abierto=horario.abierto,
        hora_apertura=horario.hora_apertura,
        hora_cierre=horario.hora_cierre,
    )


@enrutador_portal.get("", response_model=PortalRespuesta, summary="Contenido del portal")
def ver_portal(sesion: SesionBD) -> PortalRespuesta:
    """Misión, visión, contacto y horarios de atención, en una sola petición. Público."""
    portal = servicio.obtener_portal(sesion)
    return PortalRespuesta(
        secciones=[SeccionRespuesta.model_validate(s) for s in portal.secciones],
        horarios=[_horario(h) for h in portal.horarios],
    )


@enrutador_portal.put(
    "/secciones/{seccion}",
    response_model=SeccionRespuesta,
    summary="Editar una sección (administrador)",
    responses=respuestas_error(401, 403, 422),
)
def editar_seccion(
    sesion: SesionBD, administrador: SoloAdministrador, seccion: SeccionPortal, datos: SeccionEditar
) -> SeccionRespuesta:
    """Crea o reemplaza el título y el texto de la sección."""
    registro = servicio.guardar_seccion(sesion, seccion, datos, administrador)
    return SeccionRespuesta.model_validate(registro)


@enrutador_portal.put(
    "/horarios/{dia}",
    response_model=HorarioDia,
    summary="Abrir un día o cambiar su horario (administrador)",
    responses=respuestas_error(401, 403, 422),
)
def editar_horario(
    sesion: SesionBD, administrador: SoloAdministrador, dia: DiaSemana, datos: HorarioEditar
) -> HorarioDia:
    return _horario(servicio.guardar_horario(sesion, dia, datos, administrador))


@enrutador_portal.delete(
    "/horarios/{dia}",
    response_model=HorarioDia,
    summary="Cerrar un día (administrador)",
    responses=respuestas_error(401, 403, 422),
)
def cerrar_dia(sesion: SesionBD, administrador: SoloAdministrador, dia: DiaSemana) -> HorarioDia:
    """El día queda sin atención. Si ya estaba cerrado, responde igual."""
    return _horario(servicio.cerrar_dia(sesion, dia, administrador))
