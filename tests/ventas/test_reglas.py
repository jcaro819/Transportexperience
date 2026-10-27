"""Reglas puras de las ventas: transiciones y estado vigente. No usan base de datos."""

from datetime import UTC, datetime, timedelta

import pytest

from app.modulos.ventas.estados import TRANSICIONES, es_transicion_valida, validar_transicion
from app.modulos.ventas.excepciones import TransicionDeVentaInvalida
from app.modulos.ventas.modelos import EstadoVenta, Venta
from app.modulos.ventas.servicio import estado_vigente

E = EstadoVenta
MOMENTO = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)


@pytest.mark.parametrize("nuevo", [E.PAGADA, E.CANCELADA, E.EXPIRADA])
def test_una_pendiente_puede_pagarse_cancelarse_o_expirar(nuevo: E) -> None:
    validar_transicion(E.PENDIENTE_PAGO, nuevo)


@pytest.mark.parametrize("final", [E.PAGADA, E.CANCELADA, E.EXPIRADA])
def test_los_estados_finales_no_salen(final: E) -> None:
    assert not any(es_transicion_valida(final, nuevo) for nuevo in E)
    with pytest.raises(TransicionDeVentaInvalida):
        validar_transicion(final, E.PAGADA)


def test_la_tabla_cubre_todos_los_estados() -> None:
    assert set(TRANSICIONES) == set(E)


def test_una_pendiente_vencida_se_muestra_expirada() -> None:
    vencida = Venta(estado=E.PENDIENTE_PAGO, expira_en=MOMENTO)
    vigente = Venta(estado=E.PENDIENTE_PAGO, expira_en=MOMENTO + timedelta(seconds=1))
    assert estado_vigente(vencida, MOMENTO) == E.EXPIRADA
    assert estado_vigente(vigente, MOMENTO) == E.PENDIENTE_PAGO
    assert estado_vigente(Venta(estado=E.PAGADA), MOMENTO) == E.PAGADA
