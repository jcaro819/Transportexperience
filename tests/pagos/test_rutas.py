"""Rutas de pagos: configuración, estado, comprobante PDF, webhook y devoluciones (HU-05).

Las reglas se prueban en ``test_procesamiento.py``; aquí solo el contrato HTTP.
"""

from datetime import timedelta

import pytest

from app.comun import fechas
from app.modulos.pagos.modelos import MetodoPago
from app.modulos.usuarios.modelos import Rol
from tests.conftest import encabezado_de


@pytest.fixture
def pagado(sesion, fabrica, cliente_api) -> tuple[str, dict]:
    """Un alquiler pagado por la API: devuelve la referencia del pago y el encabezado."""
    sesion.add(MetodoPago(codigo="tarjeta", nombre="Tarjeta"))
    modelo = fabrica.modelo(tarifa_diaria=30_000)
    fabrica.vehiculo(modelo)
    cliente = encabezado_de(fabrica.cliente())
    inicio = fechas.hoy() + timedelta(days=2)
    alquiler = cliente_api.post(
        "/alquileres",
        json={"modelo_id": modelo.id, "fecha_inicio": str(inicio), "fecha_fin": str(inicio)},
        headers=cliente,
    ).json()
    pago = cliente_api.post(
        f"/alquileres/{alquiler['id']}/pago", json={"metodo_pago": "tarjeta"}, headers=cliente
    ).json()
    return pago["pago"]["referencia"], cliente


def test_configuracion_es_publica(cliente_api, sesion) -> None:
    sesion.add(MetodoPago(codigo="pse", nombre="PSE"))
    cuerpo = cliente_api.get("/pagos/configuracion").json()
    assert cuerpo["proveedor"] == "falso"
    assert cuerpo["metodos"] == ["pse"]
    assert cuerpo["llave_publica"] is None


def test_bancos_pse_son_publicos(cliente_api) -> None:
    bancos = cliente_api.get("/pagos/pse/bancos").json()
    assert {"codigo": "1", "nombre": "Banco que aprueba (prueba)"} in bancos


def test_el_cliente_ve_su_pago_y_descarga_el_comprobante(cliente_api, pagado) -> None:
    referencia, cliente = pagado

    pago = cliente_api.get(f"/pagos/{referencia}", headers=cliente)
    pdf = cliente_api.get(f"/pagos/{referencia}/comprobante", headers=cliente)

    assert pago.status_code == 200
    assert pago.json()["estado"] == "aprobado"
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert referencia in pdf.headers["content-disposition"]


def test_otro_cliente_no_ve_el_pago(cliente_api, crear_usuario, pagado) -> None:
    referencia, _ = pagado
    intruso = encabezado_de(crear_usuario(Rol.CLIENTE))
    assert cliente_api.get(f"/pagos/{referencia}", headers=intruso).status_code == 404
    assert cliente_api.get(f"/pagos/{referencia}/comprobante", headers=intruso).status_code == 404


def test_el_operador_ve_el_pago(cliente_api, crear_usuario, pagado) -> None:
    referencia, _ = pagado
    operador = encabezado_de(crear_usuario(Rol.OPERADOR))
    assert cliente_api.get(f"/pagos/{referencia}", headers=operador).status_code == 200


def test_el_webhook_es_publico_y_siempre_responde_200(cliente_api) -> None:
    respuesta = cliente_api.post("/pagos/webhooks/wompi", content=b'{"event": "otro"}')
    assert respuesta.status_code == 200
    assert respuesta.json() == {"recibido": True}


def test_devoluciones_solo_para_el_administrador(cliente_api, crear_usuario) -> None:
    operador = encabezado_de(crear_usuario(Rol.OPERADOR))
    administrador = encabezado_de(crear_usuario(Rol.ADMINISTRADOR))
    assert cliente_api.get("/pagos/devoluciones-pendientes", headers=operador).status_code == 403
    assert (
        cliente_api.get("/pagos/devoluciones-pendientes", headers=administrador).status_code == 200
    )
    respuesta = cliente_api.post(
        "/pagos/NO-EXISTE/devolucion-ejecutada",
        json={"nota": "Hecha en Wompi."},
        headers=administrador,
    )
    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["codigo"] == "pago_no_encontrado"
