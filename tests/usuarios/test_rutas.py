"""Protección por rol (RBAC) y contrato HTTP de las rutas de usuarios (HU-12).

Las reglas de negocio se prueban en ``test_servicio.py``. Aquí solo se verifica lo que vive
en las rutas: quién puede entrar, el flujo de inicio de sesión y la forma de los errores.
"""

import pytest

from app.modulos.usuarios.modelos import Rol
from tests.conftest import CONTRASENA_PRUEBAS, encabezado_de

RUTAS_DE_ADMINISTRADOR = [
    ("get", "/usuarios"),
    ("post", "/usuarios"),
    ("get", "/usuarios/1"),
    ("patch", "/usuarios/1"),
]


def test_flujo_completo_registro_inicio_de_sesion_y_perfil(cliente_api) -> None:
    registro = cliente_api.post(
        "/usuarios/registro",
        json={
            "nombre_completo": "Carla",
            "correo": "carla@correo.com",
            "contrasena": "MiClave2026",
        },
    )
    assert registro.status_code == 201

    token = cliente_api.post(
        "/autenticacion/token", data={"username": "carla@correo.com", "password": "MiClave2026"}
    )
    assert token.status_code == 200
    assert token.json()["token_type"] == "bearer"
    assert token.json()["usuario"]["rol"] == "cliente"

    encabezado = {"Authorization": f"Bearer {token.json()['access_token']}"}
    perfil = cliente_api.get("/usuarios/yo", headers=encabezado)
    assert perfil.status_code == 200
    assert perfil.json()["correo"] == "carla@correo.com"
    assert "hash_contrasena" not in perfil.json()


def test_el_registro_publico_ignora_un_rol_enviado(cliente_api) -> None:
    respuesta = cliente_api.post(
        "/usuarios/registro",
        json={
            "nombre_completo": "Intento de Admin",
            "correo": "intruso@correo.com",
            "contrasena": "MiClave2026",
            "rol": "administrador",
        },
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["rol"] == "cliente"


def test_sin_token_responde_401_con_error_uniforme(cliente_api) -> None:
    respuesta = cliente_api.get("/usuarios/yo")

    assert respuesta.status_code == 401
    assert respuesta.headers["www-authenticate"] == "Bearer"
    error = respuesta.json()["error"]
    assert error["codigo"] == "no_autenticado"
    assert error["mensaje"] and error["accion"]


def test_credenciales_invalidas_responden_401(cliente_api, crear_usuario) -> None:
    crear_usuario(correo="carla@correo.com")

    respuesta = cliente_api.post(
        "/autenticacion/token", data={"username": "carla@correo.com", "password": "otra-clave"}
    )

    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["codigo"] == "credenciales_invalidas"


@pytest.mark.parametrize("rol", [Rol.CLIENTE, Rol.OPERADOR, Rol.DOMICILIARIO])
@pytest.mark.parametrize(("metodo", "ruta"), RUTAS_DE_ADMINISTRADOR)
def test_solo_el_administrador_entra_a_la_gestion_de_usuarios(
    cliente_api, crear_usuario, rol: Rol, metodo: str, ruta: str
) -> None:
    usuario = crear_usuario(rol)

    respuesta = cliente_api.request(metodo, ruta, headers=encabezado_de(usuario), json={})

    assert respuesta.status_code == 403
    assert respuesta.json()["error"]["codigo"] == "permiso_denegado"


def test_administrador_lista_usuarios_paginados(cliente_api, crear_usuario) -> None:
    admin = crear_usuario(Rol.ADMINISTRADOR)
    crear_usuario()
    crear_usuario()

    respuesta = cliente_api.get("/usuarios?tamano=2", headers=encabezado_de(admin))

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 3
    assert cuerpo["paginas"] == 2
    assert len(cuerpo["elementos"]) == 2


def test_desactivar_una_cuenta_invalida_su_token_de_inmediato(cliente_api, crear_usuario) -> None:
    admin = crear_usuario(Rol.ADMINISTRADOR)
    operador = crear_usuario(Rol.OPERADOR)
    encabezado_operador = encabezado_de(operador)
    assert cliente_api.get("/usuarios/yo", headers=encabezado_operador).status_code == 200

    desactivar = cliente_api.patch(
        f"/usuarios/{operador.id}", json={"activo": False}, headers=encabezado_de(admin)
    )
    assert desactivar.status_code == 200

    assert cliente_api.get("/usuarios/yo", headers=encabezado_operador).status_code == 401


def test_datos_invalidos_responden_422_indicando_el_campo(cliente_api) -> None:
    respuesta = cliente_api.post(
        "/usuarios/registro",
        json={"nombre_completo": "Carla", "correo": "no-es-correo", "contrasena": "corta"},
    )

    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["codigo"] == "datos_invalidos"
    assert {d["campo"] for d in error["detalles"]} == {"correo", "contrasena"}


def test_ruta_inexistente_responde_con_error_uniforme(cliente_api) -> None:
    respuesta = cliente_api.get("/no-existe")

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["codigo"] == "recurso_no_encontrado"


def test_login_con_la_contrasena_de_pruebas(cliente_api, crear_usuario) -> None:
    crear_usuario(Rol.DOMICILIARIO, correo="diego@correo.com")

    respuesta = cliente_api.post(
        "/autenticacion/token",
        data={"username": "diego@correo.com", "password": CONTRASENA_PRUEBAS},
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["usuario"]["rol"] == "domiciliario"
