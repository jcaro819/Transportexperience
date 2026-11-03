"""Rutas de HU-07: rastreo público sin datos personales, avance y cancelación por despacho."""

from decimal import Decimal

import pytest

from app.comun import fechas
from app.modulos.alquileres import servicio as alquileres
from app.modulos.domicilios import servicio
from app.modulos.domicilios.modelos import Domicilio
from app.modulos.pagos import procesamiento
from app.modulos.pagos.esquemas import PagoCrear
from app.modulos.pagos.modelos import MetodoPago
from app.modulos.pagos.pasarela import PasarelaFalsa
from app.modulos.usuarios.modelos import Rol
from tests.conftest import encabezado_de


@pytest.fixture
def asignado(sesion, fabrica, crear_usuario) -> tuple[Domicilio, object]:
    sesion.add(MetodoPago(codigo="tarjeta", nombre="Tarjeta"))
    fabrica.zona()
    modelo = fabrica.modelo(tarifa_diaria=30_000)
    fabrica.vehiculo(modelo)
    cliente = fabrica.cliente()
    cliente.telefono = "3001234567"
    hoy = fechas.hoy()
    alquiler = alquileres.crear_alquiler(sesion, cliente, modelo.id, hoy, hoy)
    domicilio = servicio.solicitar_domicilio(
        sesion,
        cliente,
        alquiler_id=alquiler.id,
        venta_id=None,
        direccion="Calle Secreta 123",
        indicaciones="Timbre 4",
        latitud=Decimal("7.119300"),
        longitud=Decimal("-73.122700"),
    ).domicilio
    procesamiento.pagar(
        sesion, cliente, PagoCrear(metodo_pago="tarjeta"), PasarelaFalsa(), alquiler_id=alquiler.id
    )
    domiciliario = crear_usuario(Rol.DOMICILIARIO)
    servicio.asignar_domiciliario(
        sesion, domicilio.id, crear_usuario(Rol.OPERADOR), domiciliario.id
    )
    return domicilio, domiciliario


def test_el_rastreo_es_publico_y_no_muestra_datos_personales(cliente_api, asignado) -> None:
    domicilio, _ = asignado

    respuesta = cliente_api.get(f"/domicilios/rastreo/{domicilio.codigo_rastreo}")  # sin token

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert set(cuerpo) == {"codigo_rastreo", "estado", "cambios"}
    assert all(set(c) == {"estado", "en"} for c in cuerpo["cambios"])
    assert [c["estado"] for c in cuerpo["cambios"]] == ["pendiente", "asignado"]
    texto = respuesta.text
    for dato_privado in ("Calle Secreta", "Timbre", "3001234567", "7.1193", "@prueba.co"):
        assert dato_privado not in texto


def test_rastreo_de_un_codigo_inexistente(cliente_api) -> None:
    respuesta = cliente_api.get("/domicilios/rastreo/TX-NOEXISTE")
    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["codigo"] == "domicilio_no_encontrado"


def test_el_domiciliario_avanza_por_la_api(cliente_api, asignado) -> None:
    domicilio, domiciliario = asignado
    respuesta = cliente_api.post(
        f"/domicilios/{domicilio.id}/estado",
        json={"estado": "recogido"},
        headers=encabezado_de(domiciliario),
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "recogido"


def test_estado_no_permitido_en_el_cuerpo(cliente_api, asignado) -> None:
    domicilio, domiciliario = asignado
    respuesta = cliente_api.post(
        f"/domicilios/{domicilio.id}/estado",
        json={"estado": "cancelado"},
        headers=encabezado_de(domiciliario),
    )
    assert respuesta.status_code == 422


def test_cancelacion_por_despacho_devuelve_el_envio(cliente_api, crear_usuario, asignado) -> None:
    domicilio, _ = asignado
    respuesta = cliente_api.post(
        f"/domicilios/{domicilio.id}/cancelacion-por-despacho",
        json={"motivo": "No hay domiciliarios hoy."},
        headers=encabezado_de(crear_usuario(Rol.ADMINISTRADOR)),
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["domicilio"]["estado"] == "cancelado"
    assert cuerpo["devolucion"]["tipo"] == "compensacion"
    assert cuerpo["devolucion"]["monto"] == 5_000
