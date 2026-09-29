"""Verifica que la estructura de paquetes del monolito modular esté completa."""

import importlib

import pytest

MODULOS = [
    "usuarios",
    "inventario",
    "alquileres",
    "ventas",
    "pagos",
    "domicilios",
    "rastreo",
    "reportes",
]


@pytest.mark.parametrize("modulo", MODULOS)
def test_modulo_importable(modulo: str) -> None:
    paquete = importlib.import_module(f"app.modulos.{modulo}")
    assert paquete.__doc__, f"El módulo {modulo} debe documentar qué historias cubre"
