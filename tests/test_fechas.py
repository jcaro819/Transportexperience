"""Fecha y hora de negocio en Colombia (sin base de datos)."""

from datetime import timedelta

from app.comun import fechas


def test_ahora_esta_en_hora_de_colombia() -> None:
    assert fechas.ahora().utcoffset() == timedelta(hours=-5)


def test_hoy_es_la_fecha_de_colombia() -> None:
    assert fechas.hoy() == fechas.ahora().date()
