"""Reglas puras de los alquileres: tarifa, fechas, estados. No usan base de datos."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.modulos.alquileres.estados import TRANSICIONES, es_transicion_valida, validar_transicion
from app.modulos.alquileres.excepciones import DuracionExcedida, TransicionDeAlquilerInvalida
from app.modulos.alquileres.modelos import Alquiler, EstadoAlquiler
from app.modulos.alquileres.servicio import (
    calcular_subtotal,
    esta_vencido,
    estado_vigente,
    validar_fechas,
)
from app.modulos.inventario.excepciones import FechasInvalidas

HOY = date(2026, 11, 2)
MOMENTO = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
E = EstadoAlquiler


# --- Tarifa por días inclusivos ---


def test_del_5_al_7_son_tres_dias() -> None:
    assert calcular_subtotal(30_000, date(2026, 11, 5), date(2026, 11, 7)) == 90_000


def test_un_solo_dia_cobra_un_dia() -> None:
    assert calcular_subtotal(30_000, date(2026, 11, 5), date(2026, 11, 5)) == 30_000


def test_el_rango_puede_cruzar_de_mes() -> None:
    assert calcular_subtotal(25_000, date(2026, 11, 29), date(2026, 12, 2)) == 4 * 25_000


def test_el_subtotal_es_entero() -> None:
    assert isinstance(calcular_subtotal(33_333, date(2026, 11, 5), date(2026, 11, 7)), int)


# --- Fechas y máximo de días ---


def test_acepta_empezar_hoy() -> None:
    validar_fechas(HOY, HOY, HOY, max_dias=30)


def test_rechaza_inicio_en_el_pasado() -> None:
    with pytest.raises(FechasInvalidas, match="ya pasó"):
        validar_fechas(HOY - timedelta(days=1), HOY, HOY, max_dias=30)


def test_rechaza_fin_antes_del_inicio() -> None:
    with pytest.raises(FechasInvalidas, match="anterior"):
        validar_fechas(HOY + timedelta(days=3), HOY + timedelta(days=2), HOY, max_dias=30)


def test_acepta_exactamente_el_maximo_de_dias() -> None:
    validar_fechas(HOY, HOY + timedelta(days=29), HOY, max_dias=30)  # 30 días inclusivos


def test_rechaza_un_dia_mas_del_maximo() -> None:
    with pytest.raises(DuracionExcedida, match="31 días.*30"):
        validar_fechas(HOY, HOY + timedelta(days=30), HOY, max_dias=30)


# --- Estado vigente: un pendiente vencido se muestra expirado ---


def _pendiente(expira_en: datetime) -> Alquiler:
    return Alquiler(estado=E.PENDIENTE_PAGO, expira_en=expira_en)


def test_pendiente_dentro_del_bloqueo_sigue_pendiente() -> None:
    alquiler = _pendiente(MOMENTO + timedelta(minutes=1))
    assert not esta_vencido(alquiler, MOMENTO)
    assert estado_vigente(alquiler, MOMENTO) == E.PENDIENTE_PAGO


def test_pendiente_vencido_se_muestra_expirado() -> None:
    alquiler = _pendiente(MOMENTO)
    assert esta_vencido(alquiler, MOMENTO)
    assert estado_vigente(alquiler, MOMENTO) == E.EXPIRADO


def test_un_confirmado_nunca_vence() -> None:
    assert estado_vigente(Alquiler(estado=E.CONFIRMADO), MOMENTO) == E.CONFIRMADO


# --- Transiciones ---


@pytest.mark.parametrize(
    ("actual", "nuevo"),
    [
        (E.PENDIENTE_PAGO, E.CONFIRMADO),
        (E.PENDIENTE_PAGO, E.CANCELADO),
        (E.PENDIENTE_PAGO, E.EXPIRADO),
        (E.CONFIRMADO, E.EN_CURSO),
        (E.CONFIRMADO, E.CANCELADO),  # solo el administrador, con devolución (HU-05)
        (E.EN_CURSO, E.FINALIZADO),
    ],
)
def test_transiciones_validas(actual: E, nuevo: E) -> None:
    validar_transicion(actual, nuevo)


@pytest.mark.parametrize(
    ("actual", "nuevo"),
    [
        (E.PENDIENTE_PAGO, E.EN_CURSO),  # no se entrega sin pagar
        (E.EN_CURSO, E.CANCELADO),
        (E.EXPIRADO, E.CONFIRMADO),  # un pago tardío no revive la reserva
    ],
)
def test_transiciones_invalidas(actual: E, nuevo: E) -> None:
    with pytest.raises(TransicionDeAlquilerInvalida):
        validar_transicion(actual, nuevo)


@pytest.mark.parametrize("final", [E.FINALIZADO, E.CANCELADO, E.EXPIRADO])
def test_los_estados_finales_no_salen(final: E) -> None:
    assert not any(es_transicion_valida(final, nuevo) for nuevo in E)


def test_la_tabla_cubre_todos_los_estados() -> None:
    assert set(TRANSICIONES) == set(E)
