"""Rutas de alquileres: permisos por rol y forma de las respuestas (HU-03).

Las reglas se prueban en ``test_servicio.py``; aquí solo el contrato HTTP.
"""

from datetime import timedelta

import pytest

from app.comun import fechas
from app.modulos.pagos.modelos import MetodoPago
from app.modulos.usuarios.modelos import Rol
from tests.conftest import encabezado_de


@pytest.fixture
def modelo(sesion, fabrica):
    sesion.add(MetodoPago(codigo="tarjeta", nombre="Tarjeta"))
    modelo = fabrica.modelo(tarifa_diaria=30_000)
    fabrica.vehiculo(modelo, codigo="RUT-0001")
    return modelo


def _cuerpo(modelo, dias: int = 3) -> dict:
    inicio = fechas.hoy() + timedelta(days=2)
    return {
        "modelo_id": modelo.id,
        "fecha_inicio": inicio.isoformat(),
        "fecha_fin": (inicio + timedelta(days=dias - 1)).isoformat(),
    }


def test_flujo_completo_reservar_pagar_y_consultar(cliente_api, fabrica, modelo) -> None:
    cliente = encabezado_de(fabrica.cliente())

    reserva = cliente_api.post("/alquileres", json=_cuerpo(modelo), headers=cliente)
    assert reserva.status_code == 201
    alquiler = reserva.json()
    assert alquiler["estado"] == "pendiente_pago"
    assert alquiler["vehiculo"]["codigo"] == "RUT-0001"
    assert (alquiler["dias"], alquiler["total"]) == (3, 90_000)
    assert alquiler["expira_en"] is not None

    pago = cliente_api.post(
        f"/alquileres/{alquiler['id']}/pago", json={"metodo_pago": "Tarjeta"}, headers=cliente
    )
    assert pago.status_code == 201
    assert pago.json()["pago"]["estado"] == "aprobado"
    assert pago.json()["alquiler"]["estado"] == "confirmado"

    mios = cliente_api.get("/alquileres/mios", headers=cliente).json()
    assert [a["id"] for a in mios["elementos"]] == [alquiler["id"]]
    assert cliente_api.get(f"/alquileres/{alquiler['id']}", headers=cliente).status_code == 200


def test_sin_sesion_no_se_reserva(cliente_api, modelo) -> None:
    respuesta = cliente_api.post("/alquileres", json=_cuerpo(modelo))
    assert respuesta.status_code == 401


@pytest.mark.parametrize("rol", [Rol.OPERADOR, Rol.ADMINISTRADOR, Rol.DOMICILIARIO])
def test_solo_el_cliente_reserva(cliente_api, crear_usuario, modelo, rol) -> None:
    respuesta = cliente_api.post(
        "/alquileres", json=_cuerpo(modelo), headers=encabezado_de(crear_usuario(rol))
    )
    assert respuesta.status_code == 403


def test_error_de_negocio_con_la_forma_uniforme(cliente_api, fabrica, modelo) -> None:
    respuesta = cliente_api.post(
        "/alquileres", json=_cuerpo(modelo, dias=31), headers=encabezado_de(fabrica.cliente())
    )
    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["codigo"] == "duracion_excedida"
    assert "30" in error["mensaje"]
    assert error["accion"]


def test_el_cliente_no_ve_la_lista_del_mostrador(cliente_api, fabrica, modelo) -> None:
    cliente = encabezado_de(fabrica.cliente())
    assert cliente_api.get("/alquileres", headers=cliente).status_code == 403
    assert cliente_api.get("/alquileres/en-riesgo", headers=cliente).status_code == 403


def test_el_operador_lista_entrega_y_recibe(cliente_api, fabrica, crear_usuario, modelo) -> None:
    cliente = encabezado_de(fabrica.cliente())
    operador = encabezado_de(crear_usuario(Rol.OPERADOR))
    cuerpo = _cuerpo(modelo) | {"fecha_inicio": fechas.hoy().isoformat()}
    alquiler_id = cliente_api.post("/alquileres", json=cuerpo, headers=cliente).json()["id"]
    cliente_api.post(
        f"/alquileres/{alquiler_id}/pago", json={"metodo_pago": "tarjeta"}, headers=cliente
    )

    lista = cliente_api.get("/alquileres?estado=confirmado", headers=operador).json()
    assert [a["id"] for a in lista["elementos"]] == [alquiler_id]

    entrega = cliente_api.post(f"/alquileres/{alquiler_id}/entrega", headers=operador)
    assert entrega.json()["estado"] == "en_curso"
    assert entrega.json()["vehiculo"]["estado"] == "alquilado"

    devolucion = cliente_api.post(f"/alquileres/{alquiler_id}/devolucion", headers=operador)
    assert devolucion.json()["estado"] == "finalizado"
    assert devolucion.json()["vehiculo"]["estado"] == "disponible"


def test_el_operador_no_reasigna(cliente_api, crear_usuario) -> None:
    respuesta = cliente_api.post(
        "/alquileres/1/reasignacion", json={}, headers=encabezado_de(crear_usuario(Rol.OPERADOR))
    )
    assert respuesta.status_code == 403
