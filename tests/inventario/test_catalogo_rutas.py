"""Contrato HTTP del catálogo (HU-02): es público y responde con los formatos acordados.

Las reglas de disponibilidad se prueban en ``test_catalogo_servicio.py``.
"""

from datetime import timedelta

from app.comun.fechas import hoy
from app.modulos.inventario.modelos import EstadoVehiculo


def test_el_catalogo_es_publico_y_paginado(cliente_api, fabrica) -> None:
    modelo = fabrica.modelo(tarifa_diaria=60_000, precio_venta=2_400_000)
    fabrica.vehiculo(modelo, nivel_bateria=90)
    fabrica.vehiculo(modelo, EstadoVehiculo.MANTENIMIENTO)

    respuesta = cliente_api.get("/catalogo/modelos")  # sin token

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 1
    [ficha] = cuerpo["elementos"]
    assert ficha["tarifa_diaria"] == 60_000
    assert ficha["se_alquila"] and ficha["se_vende"]
    assert ficha["disponibles_hoy"] == 1
    assert ficha["tipo"]["nombre"]


def test_detalle_y_disponibilidad_por_fechas(cliente_api, fabrica) -> None:
    modelo = fabrica.modelo()
    fabrica.vehiculo(modelo, codigo="MON-0001", nivel_bateria=77)
    inicio, fin = hoy() + timedelta(days=2), hoy() + timedelta(days=4)

    detalle = cliente_api.get(f"/catalogo/modelos/{modelo.id}")
    rango = cliente_api.get(
        f"/catalogo/modelos/{modelo.id}/disponibilidad",
        params={"fecha_inicio": inicio.isoformat(), "fecha_fin": fin.isoformat()},
    )

    assert detalle.status_code == 200
    assert detalle.json()["unidades_disponibles"] == [
        {"codigo": "MON-0001", "ubicacion": None, "nivel_bateria": 77}
    ]
    assert rango.status_code == 200
    assert rango.json()["dias"] == 3
    assert rango.json()["unidades_libres"] == 1


def test_filtros_invalidos_responden_con_error_uniforme(cliente_api) -> None:
    invertido = cliente_api.get("/catalogo/modelos?tarifa_min=50000&tarifa_max=1000")
    negativo = cliente_api.get("/catalogo/modelos?tarifa_min=-5")

    assert invertido.status_code == 422
    assert invertido.json()["error"]["codigo"] == "rango_de_tarifa_invalido"
    assert negativo.status_code == 422
    assert negativo.json()["error"]["detalles"][0]["campo"] == "tarifa_min"


def test_modelo_inexistente_responde_404_con_error_uniforme(cliente_api) -> None:
    respuesta = cliente_api.get("/catalogo/modelos/999999")

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["codigo"] == "modelo_no_encontrado"


def test_fechas_en_el_pasado_responden_422(cliente_api, fabrica) -> None:
    modelo = fabrica.modelo()
    ayer = (hoy() - timedelta(days=1)).isoformat()

    respuesta = cliente_api.get(
        f"/catalogo/modelos/{modelo.id}/disponibilidad",
        params={"fecha_inicio": ayer, "fecha_fin": ayer},
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["error"]["codigo"] == "fechas_invalidas"


def test_tipos_de_vehiculo_para_el_filtro(cliente_api, fabrica) -> None:
    fabrica.tipo("Cicla")
    fabrica.tipo("Patín", activo=False)

    respuesta = cliente_api.get("/catalogo/tipos")

    assert [t["nombre"] for t in respuesta.json()["elementos"]] == ["Cicla"]
