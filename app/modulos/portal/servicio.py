"""Reglas de negocio del portal institucional (HU-01) y los horarios de atención (SRS 3.5.3).

Lectura pública; edición solo del administrador, con auditoría (SRS 3.5.4).
"""

from dataclasses import dataclass
from datetime import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auditoria import registrar_auditoria
from app.comun.errores import PermisoDenegado
from app.modulos.portal.esquemas import HorarioEditar, SeccionEditar
from app.modulos.portal.modelos import ContenidoPortal, DiaSemana, HorarioAtencion, SeccionPortal
from app.modulos.usuarios.modelos import Rol, Usuario


@dataclass(frozen=True)
class Horario:
    dia: DiaSemana
    hora_apertura: time | None
    hora_cierre: time | None

    @property
    def abierto(self) -> bool:
        return self.hora_apertura is not None


@dataclass(frozen=True)
class Portal:
    secciones: list[ContenidoPortal]
    horarios: list[Horario]


def _exigir_administrador(usuario: Usuario) -> None:
    # Las rutas ya lo exigen; el servicio lo repite para que ninguna llamada futura lo salte.
    if usuario.rol != Rol.ADMINISTRADOR:
        raise PermisoDenegado()


def _horario_json(horario: HorarioAtencion | None) -> dict[str, str] | None:
    if horario is None:
        return None
    return {
        "hora_apertura": horario.hora_apertura.isoformat(),
        "hora_cierre": horario.hora_cierre.isoformat(),
    }


def obtener_portal(sesion: Session) -> Portal:
    """Contenido institucional y horarios de los 7 días. Dos consultas pequeñas."""
    orden = list(SeccionPortal)
    secciones = sesion.scalars(
        select(ContenidoPortal).where(ContenidoPortal.seccion.in_(orden))
    ).all()
    secciones = sorted(secciones, key=lambda s: orden.index(SeccionPortal(s.seccion)))

    por_dia = {h.dia_semana: h for h in sesion.scalars(select(HorarioAtencion))}
    horarios = [
        Horario(
            dia=dia,
            hora_apertura=por_dia[dia.numero].hora_apertura if dia.numero in por_dia else None,
            hora_cierre=por_dia[dia.numero].hora_cierre if dia.numero in por_dia else None,
        )
        for dia in DiaSemana
    ]
    return Portal(list(secciones), horarios)


def guardar_seccion(
    sesion: Session, seccion: SeccionPortal, datos: SeccionEditar, administrador: Usuario
) -> ContenidoPortal:
    """Crea o reemplaza el texto de una sección. Queda en auditoría con antes y después."""
    _exigir_administrador(administrador)
    registro = sesion.scalars(
        select(ContenidoPortal).where(ContenidoPortal.seccion == seccion).with_for_update()
    ).one_or_none()
    antes = None
    if registro is None:
        registro = ContenidoPortal(seccion=seccion.value)
        sesion.add(registro)
    else:
        antes = {"titulo": registro.titulo, "contenido": registro.contenido}

    registro.titulo = datos.titulo
    registro.contenido = datos.contenido
    sesion.flush()
    registrar_auditoria(
        sesion,
        usuario_id=administrador.id,
        accion="crear" if antes is None else "actualizar",
        entidad="contenido_portal",
        entidad_id=seccion.value,
        antes=antes,
        despues={"titulo": datos.titulo, "contenido": datos.contenido},
    )
    sesion.commit()
    sesion.refresh(registro)  # trae actualizado_en calculado por la base
    return registro


def guardar_horario(
    sesion: Session, dia: DiaSemana, datos: HorarioEditar, administrador: Usuario
) -> Horario:
    """Abre un día o cambia su horario. Queda en auditoría."""
    _exigir_administrador(administrador)
    registro = sesion.scalars(
        select(HorarioAtencion).where(HorarioAtencion.dia_semana == dia.numero).with_for_update()
    ).one_or_none()
    antes = _horario_json(registro)
    if registro is None:
        registro = HorarioAtencion(dia_semana=dia.numero)
        sesion.add(registro)

    registro.hora_apertura = datos.hora_apertura
    registro.hora_cierre = datos.hora_cierre
    sesion.flush()
    registrar_auditoria(
        sesion,
        usuario_id=administrador.id,
        accion="crear" if antes is None else "actualizar",
        entidad="horarios_atencion",
        entidad_id=dia.value,
        antes=antes,
        despues=_horario_json(registro),
    )
    sesion.commit()
    return Horario(dia, registro.hora_apertura, registro.hora_cierre)


def cerrar_dia(sesion: Session, dia: DiaSemana, administrador: Usuario) -> Horario:
    """Deja el día sin atención. Si ya estaba cerrado, no hace nada (ni audita)."""
    _exigir_administrador(administrador)
    registro = sesion.scalars(
        select(HorarioAtencion).where(HorarioAtencion.dia_semana == dia.numero).with_for_update()
    ).one_or_none()
    if registro is not None:
        registrar_auditoria(
            sesion,
            usuario_id=administrador.id,
            accion="eliminar",
            entidad="horarios_atencion",
            entidad_id=dia.value,
            antes=_horario_json(registro),
        )
        sesion.delete(registro)
        sesion.commit()
    return Horario(dia, None, None)
