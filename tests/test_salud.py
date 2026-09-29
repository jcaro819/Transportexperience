"""Chequeo de salud de la API (/salud)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db import obtener_sesion
from app.main import app


@pytest.mark.usefixtures("base_datos_pruebas")
def test_salud_responde_ok_con_base_disponible() -> None:
    with TestClient(app) as cliente:
        respuesta = cliente.get("/salud")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok", "base_datos": "ok"}


def test_salud_responde_503_si_la_base_no_contesta() -> None:
    class SesionCaida:
        def execute(self, *_args, **_kwargs):
            raise OperationalError("SELECT 1", {}, Exception("sin conexión"))

    app.dependency_overrides[obtener_sesion] = lambda: SesionCaida()
    try:
        with TestClient(app) as cliente:
            respuesta = cliente.get("/salud")
    finally:
        app.dependency_overrides.clear()

    assert respuesta.status_code == 503
    assert respuesta.json() == {"estado": "degradado", "base_datos": "sin_conexion"}


def test_el_frontend_en_desarrollo_puede_llamar_a_la_api() -> None:
    with TestClient(app) as cliente:
        respuesta = cliente.options(
            "/usuarios/yo",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )

    assert respuesta.status_code == 200
    assert respuesta.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_un_origen_no_autorizado_no_recibe_permiso_cors() -> None:
    with TestClient(app) as cliente:
        respuesta = cliente.options(
            "/usuarios/yo",
            headers={"Origin": "https://sitio-ajeno.com", "Access-Control-Request-Method": "GET"},
        )

    assert "access-control-allow-origin" not in respuesta.headers
