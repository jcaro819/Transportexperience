"""Validación de la configuración al arrancar."""

import pytest
from pydantic import ValidationError

from app.config import Configuracion

BASICA = {"database_url": "sqlite:///:memory:", "jwt_secreto": "x"}


def test_acepta_llaves_de_sandbox_de_wompi() -> None:
    config = Configuracion(
        _env_file=None,
        **BASICA,
        wompi_llave_publica="pub_test_abc",
        wompi_llave_privada="prv_test_abc",
    )
    assert config.wompi_llave_publica == "pub_test_abc"


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("wompi_llave_publica", "pub_prod_abc"), ("wompi_llave_privada", "prv_prod_abc")],
)
def test_rechaza_llaves_de_produccion_de_wompi(campo: str, valor: str) -> None:
    with pytest.raises(ValidationError, match="sandbox"):
        Configuracion(_env_file=None, **BASICA, **{campo: valor})


def test_rechaza_fuente_gps_desconocida() -> None:
    with pytest.raises(ValidationError):
        Configuracion(_env_file=None, **BASICA, gps_fuente="satelite")
