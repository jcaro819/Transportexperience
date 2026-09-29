"""Reglas de negocio de usuarios, autenticación y roles (HU-12), contra Postgres."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auditoria import RegistroAuditoria
from app.comun.paginacion import ParametrosPagina
from app.modulos.usuarios import servicio
from app.modulos.usuarios.esquemas import RegistroCliente, UsuarioActualizar, UsuarioCrear
from app.modulos.usuarios.excepciones import (
    CambioSobreSiMismo,
    CorreoYaRegistrado,
    CredencialesInvalidas,
    CuentaInactiva,
    UsuarioNoEncontrado,
)
from app.modulos.usuarios.modelos import Rol
from app.seguridad import leer_token
from tests.conftest import CONTRASENA_PRUEBAS


def _registro(correo: str = "nueva@correo.com") -> RegistroCliente:
    return RegistroCliente(nombre_completo="Nueva Clienta", correo=correo, contrasena="MiClave2026")


def _auditoria(sesion: Session, usuario_id: int) -> list[RegistroAuditoria]:
    consulta = select(RegistroAuditoria).filter_by(entidad="usuarios", entidad_id=str(usuario_id))
    return list(sesion.scalars(consulta))


# --- Registro -------------------------------------------------------------------------


def test_registro_crea_cliente_con_correo_normalizado_y_contrasena_cifrada(sesion) -> None:
    usuario = servicio.registrar_cliente(sesion, _registro("  Nueva@Correo.COM "))

    assert usuario.rol == Rol.CLIENTE
    assert usuario.correo == "nueva@correo.com"
    assert usuario.activo
    assert usuario.hash_contrasena.startswith("$2b$")
    assert "MiClave2026" not in usuario.hash_contrasena


def test_registro_rechaza_correo_repetido_sin_importar_mayusculas(sesion) -> None:
    servicio.registrar_cliente(sesion, _registro("repetido@correo.com"))

    with pytest.raises(CorreoYaRegistrado):
        servicio.registrar_cliente(sesion, _registro("REPETIDO@correo.com"))


# --- Autenticación --------------------------------------------------------------------


def test_autentica_con_credenciales_correctas(sesion, crear_usuario) -> None:
    usuario = crear_usuario(correo="carla@correo.com")

    assert servicio.autenticar(sesion, "Carla@Correo.com", CONTRASENA_PRUEBAS) == usuario


@pytest.mark.parametrize(
    ("correo", "contrasena"),
    [("carla@correo.com", "ContrasenaEquivocada"), ("nadie@correo.com", CONTRASENA_PRUEBAS)],
    ids=["contrasena_equivocada", "correo_inexistente"],
)
def test_mismo_error_si_falla_el_correo_o_la_contrasena(
    sesion, crear_usuario, correo: str, contrasena: str
) -> None:
    crear_usuario(correo="carla@correo.com")

    with pytest.raises(CredencialesInvalidas):
        servicio.autenticar(sesion, correo, contrasena)


def test_cuenta_inactiva_no_inicia_sesion(sesion, crear_usuario) -> None:
    crear_usuario(correo="inactiva@correo.com", activo=False)

    with pytest.raises(CuentaInactiva):
        servicio.autenticar(sesion, "inactiva@correo.com", CONTRASENA_PRUEBAS)


def test_cuenta_inactiva_no_se_revela_sin_la_contrasena_correcta(sesion, crear_usuario) -> None:
    crear_usuario(correo="inactiva@correo.com", activo=False)

    with pytest.raises(CredencialesInvalidas):
        servicio.autenticar(sesion, "inactiva@correo.com", "ContrasenaEquivocada")


def test_iniciar_sesion_emite_token_del_usuario(sesion, crear_usuario) -> None:
    usuario = crear_usuario(Rol.OPERADOR, correo="op@correo.com")

    resultado = servicio.iniciar_sesion(sesion, "op@correo.com", CONTRASENA_PRUEBAS)

    assert leer_token(resultado.token) == usuario.id
    assert resultado.expira_en_segundos == 60 * 60


# --- Gestión por el administrador -----------------------------------------------------


def test_administrador_crea_usuario_con_rol_y_queda_en_auditoria(sesion, crear_usuario) -> None:
    admin = crear_usuario(Rol.ADMINISTRADOR)
    datos = UsuarioCrear(
        nombre_completo="Diego Domiciliario",
        correo="diego@correo.com",
        contrasena="MiClave2026",
        rol=Rol.DOMICILIARIO,
    )

    usuario = servicio.crear_usuario(sesion, datos, admin)

    assert usuario.rol == Rol.DOMICILIARIO
    [registro] = _auditoria(sesion, usuario.id)
    assert registro.usuario_id == admin.id
    assert registro.accion == "crear"
    assert registro.datos_nuevos == {"correo": "diego@correo.com", "rol": "domiciliario"}


def test_cambio_de_rol_queda_en_auditoria_con_antes_y_despues(sesion, crear_usuario) -> None:
    admin = crear_usuario(Rol.ADMINISTRADOR)
    usuario = crear_usuario(Rol.CLIENTE)

    servicio.actualizar_usuario(sesion, usuario.id, UsuarioActualizar(rol=Rol.OPERADOR), admin)

    assert usuario.rol == Rol.OPERADOR
    [registro] = _auditoria(sesion, usuario.id)
    assert registro.datos_anteriores == {"rol": "cliente"}
    assert registro.datos_nuevos == {"rol": "operador"}


def test_cambio_de_nombre_no_genera_auditoria(sesion, crear_usuario) -> None:
    admin = crear_usuario(Rol.ADMINISTRADOR)
    usuario = crear_usuario()

    cambios = UsuarioActualizar(nombre_completo="Nombre Corregido")
    servicio.actualizar_usuario(sesion, usuario.id, cambios, admin)

    assert usuario.nombre_completo == "Nombre Corregido"
    assert _auditoria(sesion, usuario.id) == []


def test_solo_cambian_los_campos_enviados_y_telefono_null_lo_borra(sesion, crear_usuario) -> None:
    admin = crear_usuario(Rol.ADMINISTRADOR)
    usuario = crear_usuario()
    usuario.telefono = "3001234567"
    nombre = usuario.nombre_completo

    cambios = UsuarioActualizar.model_validate({"telefono": None})
    servicio.actualizar_usuario(sesion, usuario.id, cambios, admin)

    assert usuario.telefono is None
    assert usuario.nombre_completo == nombre
    assert usuario.rol == Rol.CLIENTE


@pytest.mark.parametrize(
    "cambios",
    [UsuarioActualizar(activo=False), UsuarioActualizar(rol=Rol.OPERADOR)],
    ids=["desactivarse", "quitarse_admin"],
)
def test_administrador_no_puede_bloquearse_a_si_mismo(
    sesion, crear_usuario, cambios: UsuarioActualizar
) -> None:
    admin = crear_usuario(Rol.ADMINISTRADOR)

    with pytest.raises(CambioSobreSiMismo):
        servicio.actualizar_usuario(sesion, admin.id, cambios, admin)

    assert admin.activo
    assert admin.rol == Rol.ADMINISTRADOR


def test_administrador_puede_editar_su_propio_nombre(sesion, crear_usuario) -> None:
    admin = crear_usuario(Rol.ADMINISTRADOR)

    cambios = UsuarioActualizar(nombre_completo="Ana Admin", rol=Rol.ADMINISTRADOR)
    servicio.actualizar_usuario(sesion, admin.id, cambios, admin)

    assert admin.nombre_completo == "Ana Admin"


def test_usuario_inexistente(sesion, crear_usuario) -> None:
    admin = crear_usuario(Rol.ADMINISTRADOR)

    with pytest.raises(UsuarioNoEncontrado):
        servicio.actualizar_usuario(sesion, 999_999, UsuarioActualizar(activo=False), admin)


# --- Listado --------------------------------------------------------------------------


def test_listado_paginado_con_total_y_paginas(sesion, crear_usuario) -> None:
    for _ in range(5):
        crear_usuario()

    pagina = servicio.listar_usuarios(sesion, ParametrosPagina(pagina=2, tamano=2))

    assert pagina.total == 5
    assert pagina.paginas == 3
    assert len(pagina.elementos) == 2


def test_listado_filtra_por_rol_estado_y_busqueda(sesion, crear_usuario) -> None:
    crear_usuario(Rol.OPERADOR, correo="op.activo@correo.com")
    crear_usuario(Rol.OPERADOR, correo="op.inactivo@correo.com", activo=False)
    crear_usuario(Rol.CLIENTE, correo="cliente@correo.com")
    todos = ParametrosPagina()

    operadores = servicio.listar_usuarios(sesion, todos, rol=Rol.OPERADOR)
    activos = servicio.listar_usuarios(sesion, todos, rol=Rol.OPERADOR, activo=True)
    buscados = servicio.listar_usuarios(sesion, todos, busqueda="INACTIVO")

    assert operadores.total == 2
    assert [u.correo for u in activos.elementos] == ["op.activo@correo.com"]
    assert [u.correo for u in buscados.elementos] == ["op.inactivo@correo.com"]
