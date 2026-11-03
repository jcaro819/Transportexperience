"""Punto dentro de polígono (HU-06): la función propia en lugar de PostGIS. Sin base de datos."""

import pytest

from app.modulos.domicilios.geometria import PoligonoInvalido, punto_en_poligono

# Cuadrado de 0 a 10 en longitud y latitud. GeoJSON: [longitud, latitud].
CUADRADO = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}


@pytest.mark.parametrize(
    ("latitud", "longitud", "esperado"),
    [
        (5, 5, True),  # centro
        (0.001, 9.999, True),  # casi en una esquina, por dentro
        (11, 5, False),  # arriba
        (5, -0.001, False),  # a la izquierda, por muy poco
        (-5, -5, False),
    ],
)
def test_cuadrado(latitud, longitud, esperado) -> None:
    assert punto_en_poligono(latitud, longitud, CUADRADO) is esperado


@pytest.mark.parametrize(
    ("latitud", "longitud"), [(0, 5), (10, 5), (5, 0), (5, 10), (0, 0), (10, 10)]
)
def test_el_borde_y_las_esquinas_cuentan_como_adentro(latitud, longitud) -> None:
    assert punto_en_poligono(latitud, longitud, CUADRADO)


def test_el_anillo_puede_venir_sin_cerrar() -> None:
    abierto = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10]]]}
    assert punto_en_poligono(5, 5, abierto)
    assert not punto_en_poligono(5, 11, abierto)


def test_poligono_concavo_en_forma_de_u() -> None:
    # Una U: el hueco del medio (x de 4 a 6, y de 4 a 10) está afuera.
    u = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [10, 0], [10, 10], [6, 10], [6, 4], [4, 4], [4, 10], [0, 10]]],
    }
    assert punto_en_poligono(8, 2, u)  # brazo izquierdo
    assert punto_en_poligono(8, 8, u)  # brazo derecho
    assert punto_en_poligono(2, 5, u)  # base
    assert not punto_en_poligono(8, 5, u)  # dentro de la U, pero fuera del polígono


def test_el_rayo_que_pasa_por_un_vertice_no_cuenta_doble() -> None:
    rombo = {"type": "Polygon", "coordinates": [[[5, 0], [10, 5], [5, 10], [0, 5]]]}
    assert punto_en_poligono(5, 2, rombo)  # el rayo pasa por el vértice (10, 5)
    assert not punto_en_poligono(5, 11, rombo)
    assert not punto_en_poligono(5, -1, rombo)  # rayo que atraviesa ambos vértices laterales


def test_un_hueco_queda_afuera_pero_su_borde_es_de_la_zona() -> None:
    con_hueco = {
        "type": "Polygon",
        "coordinates": [
            [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
            [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]],
        ],
    }
    assert punto_en_poligono(2, 2, con_hueco)
    assert not punto_en_poligono(5, 5, con_hueco)
    assert punto_en_poligono(4, 5, con_hueco)


def test_multipoligono() -> None:
    dos = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[0, 0], [1, 0], [1, 1], [0, 1]]],
            [[[5, 5], [6, 5], [6, 6], [5, 6]]],
        ],
    }
    assert punto_en_poligono(0.5, 0.5, dos)
    assert punto_en_poligono(5.5, 5.5, dos)
    assert not punto_en_poligono(3, 3, dos)


def test_zona_real_de_bucaramanga() -> None:
    # Zona "Centro" de los seeds: lat 7.11 a 7.13, lng -73.135 a -73.115.
    centro = {
        "type": "Polygon",
        "coordinates": [
            [[-73.135, 7.13], [-73.115, 7.13], [-73.115, 7.11], [-73.135, 7.11], [-73.135, 7.13]]
        ],
    }
    assert punto_en_poligono(7.1193, -73.1227, centro)  # Parque Santander, aprox.
    assert not punto_en_poligono(7.0700, -73.1050, centro)  # al sur, fuera


@pytest.mark.parametrize(
    "malo",
    [
        {"type": "Point", "coordinates": [0, 0]},
        {"type": "Polygon", "coordinates": []},
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 1]]]},
        {},
    ],
)
def test_geojson_invalido(malo) -> None:
    with pytest.raises(PoligonoInvalido):
        punto_en_poligono(0, 0, malo)
