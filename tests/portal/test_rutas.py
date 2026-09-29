"""Contrato HTTP del portal (HU-01): lectura pública, edición solo del administrador."""

import pytest

from app.modulos.usuarios.modelos import Rol
from tests.conftest import encabezado_de

EDICIONES = [
    ("put", "/portal/secciones/mision", {"titulo": "Misión", "contenido": "Texto nuevo."}),
    ("put", "/portal/horarios/lunes", {"hora_apertura": "07:00", "hora_cierre": "19:00"}),
    ("delete", "/portal/horarios/domingo", None),
]


def test_el_portal_es_publico(cliente_api) -> None:
    respuesta = cliente_api.get("/portal")  # sin token

    assert respuesta.status_code == 200
    assert len(respuesta.json()["horarios"]) == 7


def test_el_administrador_edita_y_el_publico_lo_ve(cliente_api, crear_usuario) -> None:
    admin = encabezado_de(crear_usuario(Rol.ADMINISTRADOR))

    seccion = cliente_api.put(
        "/portal/secciones/vision",
        json={"titulo": "Visión", "contenido": "Ser la referencia en movilidad liviana."},
        headers=admin,
    )
    horario = cliente_api.put(
        "/portal/horarios/sabado",
        json={"hora_apertura": "08:00", "hora_cierre": "17:00"},
        headers=admin,
    )

    assert seccion.status_code == 200
    assert horario.json() == {
        "dia": "sabado",
        "abierto": True,
        "hora_apertura": "08:00:00",
        "hora_cierre": "17:00:00",
    }
    portal = cliente_api.get("/portal").json()
    assert portal["secciones"][0]["contenido"] == "Ser la referencia en movilidad liviana."
    assert portal["horarios"][5]["abierto"]


@pytest.mark.parametrize("rol", [Rol.OPERADOR, Rol.CLIENTE, Rol.DOMICILIARIO])
@pytest.mark.parametrize(("metodo", "ruta", "cuerpo"), EDICIONES)
def test_solo_el_administrador_edita(
    cliente_api, crear_usuario, rol: Rol, metodo: str, ruta: str, cuerpo
) -> None:
    respuesta = cliente_api.request(
        metodo, ruta, json=cuerpo, headers=encabezado_de(crear_usuario(rol))
    )

    assert respuesta.status_code == 403


@pytest.mark.parametrize(("metodo", "ruta", "cuerpo"), EDICIONES)
def test_editar_sin_sesion_responde_401(cliente_api, metodo: str, ruta: str, cuerpo) -> None:
    assert cliente_api.request(metodo, ruta, json=cuerpo).status_code == 401


def test_datos_invalidos_responden_422(cliente_api, crear_usuario) -> None:
    admin = encabezado_de(crear_usuario(Rol.ADMINISTRADOR))

    invertido = cliente_api.put(
        "/portal/horarios/lunes",
        json={"hora_apertura": "19:00", "hora_cierre": "07:00"},
        headers=admin,
    )
    seccion_desconocida = cliente_api.put(
        "/portal/secciones/historia",
        json={"titulo": "Historia", "contenido": "No existe esa sección."},
        headers=admin,
    )
    dia_desconocido = cliente_api.delete("/portal/horarios/feriado", headers=admin)

    for respuesta in (invertido, seccion_desconocida, dia_desconocido):
        assert respuesta.status_code == 422
        assert respuesta.json()["error"]["codigo"] == "datos_invalidos"
