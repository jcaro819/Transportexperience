"""Validación de la configuración al arrancar."""

import pytest
from pydantic import ValidationError

from app.config import (
    LONGITUD_MINIMA_SECRETO_JWT,
    SECRETO_JWT_DE_EJEMPLO,
    Configuracion,
)
from tests.conftest import SECRETO_JWT_PRUEBAS

BASICA = {
    "database_url": "postgresql+psycopg://u:p@127.0.0.1/x",
    "jwt_secreto": SECRETO_JWT_PRUEBAS,
}


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


@pytest.mark.parametrize(
    "secreto",
    [SECRETO_JWT_DE_EJEMPLO, "corto", "a" * (LONGITUD_MINIMA_SECRETO_JWT - 1)],
    ids=["valor_de_ejemplo", "corto", "un_caracter_menos_del_minimo"],
)
def test_rechaza_secreto_jwt_inseguro(secreto: str) -> None:
    datos = {**BASICA, "jwt_secreto": secreto}

    with pytest.raises(ValidationError, match="secrets.token_urlsafe"):
        Configuracion(_env_file=None, **datos)


def test_acepta_secreto_jwt_de_la_longitud_minima() -> None:
    datos = {**BASICA, "jwt_secreto": "a" * LONGITUD_MINIMA_SECRETO_JWT}

    assert Configuracion(_env_file=None, **datos).jwt_secreto == datos["jwt_secreto"]


def test_el_error_de_configuracion_no_muestra_el_valor_del_secreto() -> None:
    secreto_corto_pero_real = "k9$Xq-casi-secreto"

    with pytest.raises(ValidationError) as error:
        Configuracion(_env_file=None, **{**BASICA, "jwt_secreto": secreto_corto_pero_real})

    assert secreto_corto_pero_real not in str(error.value)
