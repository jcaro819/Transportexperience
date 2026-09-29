"""Chequeo de salud de la API (/salud)."""

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db import obtener_sesion
from app.main import app


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
