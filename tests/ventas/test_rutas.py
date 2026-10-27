"""Rutas de ventas y del listado de productos: permisos y forma de las respuestas (HU-04).

Las reglas se prueban en ``test_servicio.py``; aquí solo el contrato HTTP.
"""

import pytest

from app.modulos.inventario.modelos import CategoriaProducto
from app.modulos.pagos.modelos import MetodoPago
from app.modulos.usuarios.modelos import Rol
from tests.conftest import encabezado_de


@pytest.fixture
def carrito(sesion, fabrica) -> dict:
    sesion.add(MetodoPago(codigo="tarjeta", nombre="Tarjeta"))
    modelo = fabrica.modelo(precio_venta=1_500_000)
    fabrica.vehiculo(modelo, codigo="VTA-0001")
    casco = fabrica.producto(nombre="Casco", precio_venta=120_000, stock=4)
    return {
        "vehiculos": [{"modelo_id": modelo.id}],
        "productos": [{"producto_id": casco.id, "cantidad": 2}],
    }


def test_productos_es_publico_y_paginado(cliente_api, fabrica) -> None:
    fabrica.producto(nombre="Cadena", categoria=CategoriaProducto.REPUESTO, stock=2)

    respuesta = cliente_api.get("/catalogo/productos?categoria=repuesto")

    assert respuesta.status_code == 200
    [producto] = respuesta.json()["elementos"]
    assert (producto["nombre"], producto["stock"], producto["categoria"]) == (
        "Cadena",
        2,
        "repuesto",
    )


def test_flujo_completo_comprar_pagar_y_comprobante(cliente_api, fabrica, carrito) -> None:
    cliente = encabezado_de(fabrica.cliente())

    compra = cliente_api.post("/ventas", json=carrito, headers=cliente)
    assert compra.status_code == 201
    venta = compra.json()
    assert venta["estado"] == "pendiente_pago"
    assert venta["total"] == 1_500_000 + 2 * 120_000
    assert {i["codigo"] for i in venta["items"] if i["tipo"] == "vehiculo"} == {"VTA-0001"}

    pago = cliente_api.post(
        f"/ventas/{venta['id']}/pago", json={"metodo_pago": "tarjeta"}, headers=cliente
    )
    assert pago.status_code == 201
    assert pago.json()["venta"]["estado"] == "pagada"
    assert pago.json()["devolucion"] is None

    comprobante = cliente_api.get(f"/ventas/{venta['id']}/comprobante", headers=cliente).json()
    assert comprobante["numero"] == f"PRE-{venta['id']:06d}"
    assert comprobante["es_preliminar"] is True
    assert comprobante["pago"]["metodo"] == "Tarjeta"
    assert comprobante["cliente"]["correo"]

    mias = cliente_api.get("/ventas/mias", headers=cliente).json()
    assert [v["id"] for v in mias["elementos"]] == [venta["id"]]


def test_carrito_vacio_o_repetido_es_invalido(cliente_api, fabrica, carrito) -> None:
    cliente = encabezado_de(fabrica.cliente())
    vacio = cliente_api.post("/ventas", json={}, headers=cliente)
    repetido = cliente_api.post(
        "/ventas", json={"productos": carrito["productos"] * 2}, headers=cliente
    )
    assert vacio.status_code == repetido.status_code == 422
    assert vacio.json()["error"]["codigo"] == "datos_invalidos"


def test_stock_insuficiente_con_error_uniforme(cliente_api, fabrica, carrito) -> None:
    carrito["productos"][0]["cantidad"] = 5
    respuesta = cliente_api.post("/ventas", json=carrito, headers=encabezado_de(fabrica.cliente()))
    assert respuesta.status_code == 409
    error = respuesta.json()["error"]
    assert error["codigo"] == "stock_insuficiente"
    assert "quedan 4" in error["mensaje"]


@pytest.mark.parametrize("rol", [Rol.OPERADOR, Rol.ADMINISTRADOR, Rol.DOMICILIARIO])
def test_solo_el_cliente_compra(cliente_api, crear_usuario, carrito, rol) -> None:
    respuesta = cliente_api.post("/ventas", json=carrito, headers=encabezado_de(crear_usuario(rol)))
    assert respuesta.status_code == 403


def test_permisos_de_los_listados(cliente_api, fabrica, crear_usuario) -> None:
    cliente = encabezado_de(fabrica.cliente())
    operador = encabezado_de(crear_usuario(Rol.OPERADOR))
    administrador = encabezado_de(crear_usuario(Rol.ADMINISTRADOR))

    assert cliente_api.get("/ventas", headers=cliente).status_code == 403
    assert cliente_api.get("/ventas", headers=operador).status_code == 200
    assert cliente_api.get("/ventas/devoluciones-pendientes", headers=operador).status_code == 403
    assert (
        cliente_api.get("/ventas/devoluciones-pendientes", headers=administrador).status_code == 200
    )
