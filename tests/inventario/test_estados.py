"""Transiciones de estado de un vehículo (CLAUDE.md 7.2), sin base de datos.

Se prueban las 36 combinaciones posibles: las permitidas pasan y todas las demás se
rechazan, sin excepción.
"""

from itertools import product

import pytest

from app.modulos.inventario.estados import es_transicion_valida, validar_transicion
from app.modulos.inventario.excepciones import TransicionInvalida
from app.modulos.inventario.modelos import EstadoVehiculo as E

PERMITIDAS = {
    (E.DISPONIBLE, E.ALQUILADO),
    (E.ALQUILADO, E.DISPONIBLE),
    (E.DISPONIBLE, E.RESERVADO),
    (E.RESERVADO, E.VENDIDO),
    (E.RESERVADO, E.DISPONIBLE),
    (E.DISPONIBLE, E.ASIGNADO_A_DOMICILIO),
    (E.ASIGNADO_A_DOMICILIO, E.DISPONIBLE),
    (E.DISPONIBLE, E.MANTENIMIENTO),
    (E.ALQUILADO, E.MANTENIMIENTO),
    (E.RESERVADO, E.MANTENIMIENTO),
    (E.ASIGNADO_A_DOMICILIO, E.MANTENIMIENTO),
    (E.MANTENIMIENTO, E.DISPONIBLE),
}
TODAS = list(product(E, E))


@pytest.mark.parametrize(("actual", "nuevo"), sorted(PERMITIDAS))
def test_transiciones_permitidas(actual: E, nuevo: E) -> None:
    validar_transicion(actual, nuevo)  # no lanza


@pytest.mark.parametrize(("actual", "nuevo"), [t for t in TODAS if t not in PERMITIDAS])
def test_todas_las_demas_transiciones_se_rechazan(actual: E, nuevo: E) -> None:
    assert not es_transicion_valida(actual, nuevo)
    with pytest.raises(TransicionInvalida):
        validar_transicion(actual, nuevo)


def test_vendido_es_terminal() -> None:
    assert not any(es_transicion_valida(E.VENDIDO, nuevo) for nuevo in E)


def test_de_mantenimiento_solo_se_sale_a_disponible() -> None:
    assert [nuevo for nuevo in E if es_transicion_valida(E.MANTENIMIENTO, nuevo)] == [E.DISPONIBLE]


def test_ningun_estado_transita_a_si_mismo() -> None:
    assert not any(es_transicion_valida(estado, estado) for estado in E)
