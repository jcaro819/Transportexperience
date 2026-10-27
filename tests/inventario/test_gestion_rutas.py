"""Rutas de la gestión del inventario (HU-10): permisos y forma de las respuestas."""

import pytest

from app.modulos.usuarios.modelos import Rol
from tests.conftest import encabezado_de


@pytest.fixture
def admin(crear_usuario):
    return encabezado_de(crear_usuario(Rol.ADMINISTRADOR))


def test_el_administrador_arma_el_inventario_por_la_api(cliente_api, admin) -> None:
    tipo = cliente_api.post(
        "/inventario/tipos", json={"nombre": "Scooter", "usa_bateria": True}, headers=admin
    )
    assert tipo.status_code == 201
    modelo = cliente_api.post(
        "/inventario/modelos",
        json={
            "tipo_vehiculo_id": tipo.json()["id"],
            "nombre": "Scooter 300",
            "tarifa_diaria": 35000,
        },
        headers=admin,
    )
    assert modelo.status_code == 201
    unidad = cliente_api.post(
        "/inventario/unidades",
        json={"codigo": "sco-0001", "modelo_id": modelo.json()["id"], "nivel_bateria": 100},
        headers=admin,
    )
    assert unidad.status_code == 201
    assert (unidad.json()["codigo"], unidad.json()["estado"]) == ("SCO-0001", "disponible")

    catalogo = cliente_api.get("/catalogo/modelos").json()
    assert "Scooter 300" in [m["nombre"] for m in catalogo["elementos"]]


def test_producto_ajuste_y_alerta(cliente_api, admin) -> None:
    producto = cliente_api.post(
        "/inventario/productos",
        json={
            "codigo": "REP-LLANTA",
            "nombre": "Llanta 10 pulgadas",
            "categoria": "repuesto",
            "precio_venta": 85000,
            "stock": 4,
            "stock_minimo": 2,
        },
        headers=admin,
    ).json()
    assert producto["bajo_stock"] is False

    ajustado = cliente_api.post(
        f"/inventario/productos/{producto['id']}/ajustes",
        json={"cantidad": -2, "motivo": "Dos llantas pinchadas."},
        headers=admin,
    ).json()
    assert (ajustado["stock"], ajustado["bajo_stock"]) == (2, True)

    alertas = cliente_api.get("/inventario/alertas-stock", headers=admin).json()
    assert [p["codigo"] for p in alertas["elementos"]] == ["REP-LLANTA"]


def test_codigo_duplicado_con_error_uniforme(cliente_api, admin, fabrica) -> None:
    fabrica.vehiculo(codigo="MON-0001")
    respuesta = cliente_api.post(
        "/inventario/unidades",
        json={"codigo": "MON-0001", "modelo_id": fabrica.modelo().id},
        headers=admin,
    )
    assert respuesta.status_code == 409
    assert respuesta.json()["error"]["codigo"] == "codigo_duplicado"


@pytest.mark.parametrize(
    ("rol", "lectura", "escritura"),
    [(Rol.OPERADOR, 200, 403), (Rol.CLIENTE, 403, 403), (Rol.DOMICILIARIO, 403, 403)],
)
def test_permisos(cliente_api, crear_usuario, rol, lectura, escritura) -> None:
    encabezado = encabezado_de(crear_usuario(rol))
    assert cliente_api.get("/inventario/resumen", headers=encabezado).status_code == lectura
    assert cliente_api.get("/inventario/alertas-stock", headers=encabezado).status_code == lectura
    crear = cliente_api.post(
        "/inventario/tipos", json={"nombre": "Scooter", "usa_bateria": True}, headers=encabezado
    )
    assert crear.status_code == escritura


def test_el_resumen_trae_todos_los_estados(cliente_api, admin, fabrica) -> None:
    fabrica.vehiculo()
    resumen = cliente_api.get("/inventario/resumen", headers=admin).json()
    assert resumen["unidades_por_estado"]["disponible"] == 1
    assert resumen["unidades_por_estado"]["vendido"] == 0
