"""Portal institucional y horarios de atención (HU-01, SRS 3.5.3), contra Postgres."""

import time as reloj
from datetime import time

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.auditoria import RegistroAuditoria
from app.comun.errores import PermisoDenegado
from app.modulos.portal import servicio
from app.modulos.portal.esquemas import HorarioEditar, SeccionEditar
from app.modulos.portal.modelos import (
    ContenidoPortal,
    DiaSemana,
    HorarioAtencion,
    SeccionPortal,
)
from app.modulos.usuarios.modelos import Rol

LIMITE_CARGA_S = 2.0  # HU-01


@pytest.fixture
def administrador(crear_usuario):
    return crear_usuario(Rol.ADMINISTRADOR)


def _auditoria(sesion, entidad: str, entidad_id: str) -> list[RegistroAuditoria]:
    consulta = (
        select(RegistroAuditoria)
        .filter_by(entidad=entidad, entidad_id=entidad_id)
        .order_by(RegistroAuditoria.id)
    )
    return list(sesion.scalars(consulta))


def _abrir(sesion, administrador, dia: DiaSemana, apertura: int, cierre: int):
    datos = HorarioEditar(hora_apertura=time(apertura), hora_cierre=time(cierre))
    return servicio.guardar_horario(sesion, dia, datos, administrador)


# --- Lectura pública ------------------------------------------------------------------


def test_el_portal_trae_las_secciones_en_orden_y_los_siete_dias(sesion) -> None:
    for seccion in ("contacto", "mision", "vision"):  # en desorden a propósito
        sesion.add(ContenidoPortal(seccion=seccion, titulo=seccion.title(), contenido="Texto."))
    sesion.add(HorarioAtencion(dia_semana=0, hora_apertura=time(7), hora_cierre=time(19)))
    sesion.flush()

    portal = servicio.obtener_portal(sesion)

    assert [s.seccion for s in portal.secciones] == ["mision", "vision", "contacto"]
    assert [h.dia for h in portal.horarios] == list(DiaSemana)
    lunes, martes, *_ = portal.horarios
    assert lunes.abierto and lunes.hora_apertura == time(7)
    assert not martes.abierto and martes.hora_apertura is None


def test_sin_contenido_el_portal_viene_vacio_y_todo_cerrado(sesion) -> None:
    portal = servicio.obtener_portal(sesion)

    assert portal.secciones == []
    assert not any(h.abierto for h in portal.horarios)


def test_el_portal_carga_en_menos_de_dos_segundos(sesion, administrador) -> None:
    for seccion in SeccionPortal:
        texto = SeccionEditar(titulo=seccion.value, contenido="Texto institucional. " * 200)
        servicio.guardar_seccion(sesion, seccion, texto, administrador)
    for dia in DiaSemana:
        _abrir(sesion, administrador, dia, 7, 19)

    inicio = reloj.perf_counter()
    servicio.obtener_portal(sesion)
    segundos = reloj.perf_counter() - inicio

    assert segundos < LIMITE_CARGA_S, f"El portal tardó {segundos:.2f} s"


# --- Edición del contenido ------------------------------------------------------------


def test_guardar_una_seccion_nueva_la_crea_y_la_audita(sesion, administrador) -> None:
    datos = SeccionEditar(titulo="Misión", contenido="Movilidad sostenible en Bucaramanga.")

    registro = servicio.guardar_seccion(sesion, SeccionPortal.MISION, datos, administrador)

    assert registro.contenido == "Movilidad sostenible en Bucaramanga."
    assert registro.actualizado_en is not None
    [auditoria] = _auditoria(sesion, "contenido_portal", "mision")
    assert auditoria.accion == "crear"
    assert auditoria.usuario_id == administrador.id
    assert auditoria.datos_anteriores is None


def test_editar_una_seccion_la_reemplaza_y_audita_antes_y_despues(sesion, administrador) -> None:
    viejo = SeccionEditar(titulo="Visión", contenido="Texto provisional.")
    nuevo = SeccionEditar(titulo="Visión", contenido="Texto oficial del equipo.")
    servicio.guardar_seccion(sesion, SeccionPortal.VISION, viejo, administrador)

    servicio.guardar_seccion(sesion, SeccionPortal.VISION, nuevo, administrador)

    [registro] = sesion.scalars(select(ContenidoPortal).filter_by(seccion="vision")).all()
    assert registro.contenido == "Texto oficial del equipo."
    _, edicion = _auditoria(sesion, "contenido_portal", "vision")
    assert edicion.accion == "actualizar"
    assert edicion.datos_anteriores == {"titulo": "Visión", "contenido": "Texto provisional."}
    assert edicion.datos_nuevos == {"titulo": "Visión", "contenido": "Texto oficial del equipo."}


@pytest.mark.parametrize("rol", [Rol.OPERADOR, Rol.CLIENTE, Rol.DOMICILIARIO])
def test_solo_el_administrador_edita_el_portal(sesion, crear_usuario, rol: Rol) -> None:
    usuario = crear_usuario(rol)
    datos = SeccionEditar(titulo="Misión", contenido="Intento de cambio.")

    with pytest.raises(PermisoDenegado):
        servicio.guardar_seccion(sesion, SeccionPortal.MISION, datos, usuario)
    with pytest.raises(PermisoDenegado):
        _abrir(sesion, usuario, DiaSemana.LUNES, 7, 19)
    with pytest.raises(PermisoDenegado):
        servicio.cerrar_dia(sesion, DiaSemana.LUNES, usuario)

    assert servicio.obtener_portal(sesion).secciones == []


# --- Horarios -------------------------------------------------------------------------


def test_abrir_un_dia_y_cambiar_su_horario_queda_auditado(sesion, administrador) -> None:
    _abrir(sesion, administrador, DiaSemana.SABADO, 8, 17)

    horario = _abrir(sesion, administrador, DiaSemana.SABADO, 9, 13)

    assert (horario.hora_apertura, horario.hora_cierre) == (time(9), time(13))
    creacion, cambio = _auditoria(sesion, "horarios_atencion", "sabado")
    assert creacion.accion == "crear"
    assert cambio.datos_anteriores == {"hora_apertura": "08:00:00", "hora_cierre": "17:00:00"}
    assert cambio.datos_nuevos == {"hora_apertura": "09:00:00", "hora_cierre": "13:00:00"}


def test_cerrar_un_dia_lo_quita_y_lo_audita(sesion, administrador) -> None:
    _abrir(sesion, administrador, DiaSemana.DOMINGO, 9, 13)

    horario = servicio.cerrar_dia(sesion, DiaSemana.DOMINGO, administrador)

    assert not horario.abierto
    domingo = servicio.obtener_portal(sesion).horarios[-1]
    assert domingo.dia == DiaSemana.DOMINGO and not domingo.abierto
    assert _auditoria(sesion, "horarios_atencion", "domingo")[-1].accion == "eliminar"


def test_cerrar_un_dia_ya_cerrado_no_hace_nada(sesion, administrador) -> None:
    servicio.cerrar_dia(sesion, DiaSemana.DOMINGO, administrador)

    assert _auditoria(sesion, "horarios_atencion", "domingo") == []


@pytest.mark.parametrize(("apertura", "cierre"), [(19, 7), (8, 8)], ids=["invertido", "igual"])
def test_el_cierre_debe_ser_posterior_a_la_apertura(apertura: int, cierre: int) -> None:
    with pytest.raises(ValidationError, match="posterior a la de apertura"):
        HorarioEditar(hora_apertura=time(apertura), hora_cierre=time(cierre))


def test_los_dias_se_numeran_como_en_la_base() -> None:
    assert DiaSemana.LUNES.numero == 0
    assert DiaSemana.DOMINGO.numero == 6
