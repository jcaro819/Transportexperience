"""Cómo se mueve un vehículo del simulador (HU-08). Lógica pura, sin red ni base de datos."""

import random
from decimal import Decimal

import pytest

from simulador_gps.movimiento import Recorrido, VehiculoSimulado, distancia_m, rango_de_velocidad
from simulador_gps.rutas import RECORRIDOS

# Caja que contiene el casco urbano de Bucaramanga (con margen).
BUCARAMANGA = {"lat": (7.06, 7.16), "lng": (-73.15, -73.08)}


def test_distancia_entre_dos_cuadras_es_realista() -> None:
    # 0,001° de latitud son ~111 m en cualquier parte.
    assert distancia_m((7.1000, -73.1100), (7.1010, -73.1100)) == pytest.approx(111.2, abs=0.5)


def test_el_recorrido_empieza_y_termina_en_sus_extremos() -> None:
    recorrido = Recorrido("prueba", [(7.10, -73.11), (7.11, -73.11)])
    assert recorrido.posicion(0) == pytest.approx((7.10, -73.11))
    assert recorrido.posicion(recorrido.longitud_m) == pytest.approx((7.11, -73.11))


def test_el_recorrido_va_y_vuelve() -> None:
    recorrido = Recorrido("prueba", [(7.10, -73.11), (7.11, -73.11)])
    ida = recorrido.posicion(recorrido.longitud_m * 0.25)
    vuelta = recorrido.posicion(recorrido.longitud_m * 1.75)
    assert ida == pytest.approx(vuelta)
    assert recorrido.posicion(recorrido.longitud_m * 2) == pytest.approx((7.10, -73.11))


@pytest.mark.parametrize(("nombre", "puntos"), RECORRIDOS.items())
def test_los_recorridos_estan_en_bucaramanga(nombre, puntos) -> None:
    for latitud, longitud in puntos:
        assert BUCARAMANGA["lat"][0] < latitud < BUCARAMANGA["lat"][1], nombre
        assert BUCARAMANGA["lng"][0] < longitud < BUCARAMANGA["lng"][1], nombre
    assert Recorrido(nombre, puntos).longitud_m > 500  # recorridos de más de 5 cuadras


@pytest.mark.parametrize(
    ("modelo", "rango"),
    [
        ("Cicla urbana 7 cambios", (12.0, 18.0)),
        ("Patín en línea", (8.0, 12.0)),
        ("Monopatín eléctrico Urbano 350", (15.0, 25.0)),  # contiene "patín": va primero
        ("Otro", (15.0, 25.0)),
    ],
)
def test_velocidad_segun_el_modelo(modelo, rango) -> None:
    assert rango_de_velocidad(modelo) == rango


def _vehiculo(descripcion="Monopatín eléctrico", semilla=7) -> VehiculoSimulado:
    recorrido = Recorrido("Carrera 27", RECORRIDOS["Carrera 27"])
    return VehiculoSimulado(
        codigo="MON-0001",
        clave="gps_x",
        recorrido=recorrido,
        descripcion=descripcion,
        azar=random.Random(semilla),
    )


def test_cada_5_segundos_avanza_una_distancia_realista() -> None:
    vehiculo = _vehiculo()
    for _ in range(200):
        antes = vehiculo.distancia_m
        cuerpo = vehiculo.avanzar(5)
        avance = vehiculo.distancia_m - antes
        assert 0 <= avance <= 25 * 1.15 / 3.6 * 5  # nunca más rápido que 28,75 km/h
        assert Decimal(cuerpo["velocidad_kmh"]) <= Decimal("28.75")


def test_las_posiciones_tienen_6_decimales_y_precision_menor_a_10_m() -> None:
    cuerpo = _vehiculo().avanzar(5)
    assert len(cuerpo["latitud"].split(".")[1]) == 6
    assert len(cuerpo["longitud"].split(".")[1]) == 6
    assert 3 <= float(cuerpo["precision_metros"]) <= 8


def test_el_error_del_gps_no_aleja_la_posicion_mas_de_10_m_de_la_calle() -> None:
    vehiculo = _vehiculo()
    for _ in range(100):
        cuerpo = vehiculo.avanzar(5)
        en_la_calle = vehiculo.recorrido.posicion(vehiculo.distancia_m)
        reportada = (float(cuerpo["latitud"]), float(cuerpo["longitud"]))
        assert distancia_m(en_la_calle, reportada) < 10


def test_la_bateria_baja_poco_a_poco_y_las_ciclas_no_la_reportan() -> None:
    monopatin = _vehiculo()
    for _ in range(100):
        cuerpo = monopatin.avanzar(5)
    assert 90 <= cuerpo["nivel_bateria"] < 100
    cicla = VehiculoSimulado(
        "CIC-0001", "gps_y", monopatin.recorrido, "Cicla urbana", usa_bateria=False
    )
    assert "nivel_bateria" not in cicla.avanzar(5)
