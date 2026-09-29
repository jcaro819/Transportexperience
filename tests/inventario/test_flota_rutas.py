"""Protección por rol y flujo HTTP de la gestión de la flota (HU-09).

Las reglas se prueban en ``test_flota_servicio.py``; aquí, quién entra y el recorrido
completo visto desde la API.
"""

import pytest

from app.modulos.usuarios.modelos import Rol
from tests.conftest import encabezado_de

REPORTAR = ("post", "/vehiculos/1/novedades")
SOLO_TALLER = [
    ("get", "/vehiculos"),
    ("get", "/vehiculos/1/novedades"),
    ("post", "/vehiculos/1/inactivacion"),
    ("post", "/vehiculos/1/novedades/1/cierre"),
]
RUTAS = [*SOLO_TALLER, REPORTAR]


@pytest.mark.parametrize(("metodo", "ruta"), RUTAS)
def test_el_cliente_no_entra_a_ninguna_ruta_de_la_flota(
    cliente_api, crear_usuario, metodo: str, ruta: str
) -> None:
    respuesta = cliente_api.request(
        metodo, ruta, headers=encabezado_de(crear_usuario(Rol.CLIENTE)), json={}
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["error"]["codigo"] == "permiso_denegado"


@pytest.mark.parametrize(("metodo", "ruta"), SOLO_TALLER)
def test_el_domiciliario_solo_puede_reportar(
    cliente_api, crear_usuario, metodo: str, ruta: str
) -> None:
    respuesta = cliente_api.request(
        metodo, ruta, headers=encabezado_de(crear_usuario(Rol.DOMICILIARIO)), json={}
    )

    assert respuesta.status_code == 403


def test_el_domiciliario_reporta_una_falla_critica_por_la_api(
    cliente_api, crear_usuario, fabrica
) -> None:
    vehiculo = fabrica.vehiculo(codigo="MON-0001")

    respuesta = cliente_api.post(
        f"/vehiculos/{vehiculo.id}/novedades",
        json={"tipo": "falla", "descripcion": "Se apagó en plena ruta.", "es_critica": True},
        headers=encabezado_de(crear_usuario(Rol.DOMICILIARIO)),
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["vehiculo"]["estado"] == "mantenimiento"


@pytest.mark.parametrize(("metodo", "ruta"), RUTAS)
def test_sin_sesion_responde_401(cliente_api, metodo: str, ruta: str) -> None:
    assert cliente_api.request(metodo, ruta, json={}).status_code == 401


def test_operador_inactiva_y_la_unidad_desaparece_del_catalogo_publico(
    cliente_api, crear_usuario, fabrica
) -> None:
    modelo = fabrica.modelo()
    vehiculo = fabrica.vehiculo(modelo, codigo="MON-0001")
    operador = encabezado_de(crear_usuario(Rol.OPERADOR))
    catalogo = f"/catalogo/modelos/{modelo.id}"
    assert cliente_api.get(catalogo).json()["disponibles_hoy"] == 1

    inactivacion = cliente_api.post(
        f"/vehiculos/{vehiculo.id}/inactivacion",
        json={"motivo": "Cambio de rodamientos."},
        headers=operador,
    )

    assert inactivacion.status_code == 201
    cuerpo = inactivacion.json()
    assert cuerpo["vehiculo"]["estado"] == "mantenimiento"
    assert cuerpo["novedad"]["estado"] == "abierta"
    assert cuerpo["alquileres_afectados"] == []
    assert cliente_api.get(catalogo).json()["disponibles_hoy"] == 0

    cierre = cliente_api.post(
        f"/vehiculos/{vehiculo.id}/novedades/{cuerpo['novedad']['id']}/cierre",
        json={"solucion": "Rodamientos nuevos.", "devolver_a_servicio": True},
        headers=operador,
    )

    assert cierre.status_code == 200
    assert cierre.json()["vehiculo"]["estado"] == "disponible"
    assert cliente_api.get(catalogo).json()["disponibles_hoy"] == 1


def test_regreso_rechazado_responde_409_con_la_causa(cliente_api, crear_usuario, fabrica) -> None:
    vehiculo = fabrica.vehiculo()
    operador = encabezado_de(crear_usuario(Rol.OPERADOR))
    novedad = cliente_api.post(
        f"/vehiculos/{vehiculo.id}/inactivacion", json={"motivo": "Frenos."}, headers=operador
    ).json()["novedad"]
    cliente_api.post(
        f"/vehiculos/{vehiculo.id}/novedades",
        json={"tipo": "falla", "descripcion": "El acelerador falla.", "es_critica": True},
        headers=operador,
    )

    respuesta = cliente_api.post(
        f"/vehiculos/{vehiculo.id}/novedades/{novedad['id']}/cierre",
        json={"solucion": "Frenos ajustados.", "devolver_a_servicio": True},
        headers=operador,
    )

    assert respuesta.status_code == 409
    error = respuesta.json()["error"]
    assert error["codigo"] == "no_puede_volver_a_servicio"
    assert "novedad(es) crítica(s) abierta(s)" in error["mensaje"]
