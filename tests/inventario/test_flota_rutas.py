"""Protección por rol y flujo HTTP de la gestión de la flota (HU-09).

Las reglas se prueban en ``test_flota_servicio.py``; aquí, quién entra y el recorrido
completo visto desde la API.
"""

import pytest

from app.modulos.usuarios.modelos import Rol
from tests.conftest import encabezado_de

RUTAS = [
    ("get", "/vehiculos"),
    ("get", "/vehiculos/1/novedades"),
    ("post", "/vehiculos/1/inactivacion"),
    ("post", "/vehiculos/1/novedades"),
    ("post", "/vehiculos/1/novedades/1/cierre"),
]


@pytest.mark.parametrize("rol", [Rol.CLIENTE, Rol.DOMICILIARIO])
@pytest.mark.parametrize(("metodo", "ruta"), RUTAS)
def test_clientes_y_domiciliarios_no_gestionan_la_flota(
    cliente_api, crear_usuario, rol: Rol, metodo: str, ruta: str
) -> None:
    respuesta = cliente_api.request(
        metodo, ruta, headers=encabezado_de(crear_usuario(rol)), json={}
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["error"]["codigo"] == "permiso_denegado"


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
        json={"tipo": "dano", "descripcion": "Rayón lateral."},
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
    assert "novedad(es) abierta(s)" in error["mensaje"]
