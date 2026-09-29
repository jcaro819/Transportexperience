"""Tokens JWT: se emiten, se leen, vencen y detectan alteraciones (sin base de datos)."""

from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from app.comun.errores import NoAutenticado, SesionExpirada
from app.modulos.usuarios.modelos import Rol, Usuario
from app.seguridad import ALGORITMO_JWT, crear_token_acceso, leer_token


def _usuario() -> Usuario:
    return Usuario(id=42, rol=Rol.OPERADOR)


def test_el_token_emitido_identifica_al_usuario() -> None:
    token, _ = crear_token_acceso(_usuario())

    assert leer_token(token) == 42


def test_token_vencido_indica_sesion_expirada() -> None:
    hace_un_dia = datetime.now(UTC) - timedelta(days=1)
    token, _ = crear_token_acceso(_usuario(), ahora=hace_un_dia)

    with pytest.raises(SesionExpirada):
        leer_token(token)


def test_token_alterado_es_rechazado() -> None:
    token, _ = crear_token_acceso(_usuario())
    cabecera, datos, firma = token.split(".")
    otra_firma = ("A" if firma[0] != "A" else "B") + firma[1:]

    with pytest.raises(NoAutenticado):
        leer_token(f"{cabecera}.{datos}.{otra_firma}")


def test_token_firmado_con_otro_secreto_es_rechazado() -> None:
    falso = jwt.encode(
        {"sub": "1", "exp": datetime.now(UTC) + timedelta(hours=1)},
        "otro-secreto",
        algorithm=ALGORITMO_JWT,
    )

    with pytest.raises(NoAutenticado):
        leer_token(falso)


def test_texto_que_no_es_token_es_rechazado() -> None:
    with pytest.raises(NoAutenticado):
        leer_token("esto-no-es-un-jwt")
