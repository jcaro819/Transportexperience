"""El webhook de pagos rechaza cuerpos demasiado grandes sin leerlos enteros (Sprint 4)."""

import asyncio

import pytest
from sqlalchemy import func, select
from starlette.requests import Request

from app.comun.peticiones import CuerpoDemasiadoGrande, leer_cuerpo_limitado
from app.modulos.pagos.modelos import EventoPago
from app.modulos.pagos.rutas import LIMITE_CUERPO_WEBHOOK


def test_un_cuerpo_demasiado_grande_responde_413_y_no_se_guarda(cliente_api, sesion) -> None:
    respuesta = cliente_api.post(
        "/pagos/webhooks/wompi", content=b"x" * (LIMITE_CUERPO_WEBHOOK + 1)
    )

    assert respuesta.status_code == 413
    assert respuesta.json()["error"]["codigo"] == "cuerpo_demasiado_grande"
    assert sesion.scalar(select(func.count()).select_from(EventoPago)) == 0


def test_un_cuerpo_normal_se_procesa(cliente_api, sesion) -> None:
    respuesta = cliente_api.post("/pagos/webhooks/wompi", content=b'{"event": "otro"}')
    assert respuesta.status_code == 200
    assert sesion.scalar(select(func.count()).select_from(EventoPago)) == 1


def _peticion(partes: list[bytes], encabezados: dict[str, str] | None = None) -> Request:
    """Una petición que entrega el cuerpo por partes, como un envío "chunked"."""
    mensajes = [
        {"type": "http.request", "body": parte, "more_body": i < len(partes) - 1}
        for i, parte in enumerate(partes)
    ]
    leidas: list[bytes] = []

    async def recibir():
        mensaje = mensajes.pop(0)
        leidas.append(mensaje["body"])
        return mensaje

    alcance = {
        "type": "http",
        "method": "POST",
        "headers": [(k.encode(), v.encode()) for k, v in (encabezados or {}).items()],
    }
    peticion = Request(alcance, recibir)
    peticion.leidas = leidas  # para comprobar cuánto se alcanzó a leer
    return peticion


def test_sin_content_length_corta_en_cuanto_pasa_el_limite() -> None:
    peticion = _peticion([b"a" * 60, b"b" * 60, b"c" * 60, b"d" * 60])

    with pytest.raises(CuerpoDemasiadoGrande):
        asyncio.run(leer_cuerpo_limitado(peticion, 100))

    assert len(peticion.leidas) == 2  # no siguió leyendo las otras partes


def test_content_length_grande_se_rechaza_sin_leer_nada() -> None:
    peticion = _peticion([b"a" * 10], {"content-length": "1000"})
    with pytest.raises(CuerpoDemasiadoGrande):
        asyncio.run(leer_cuerpo_limitado(peticion, 100))
    assert peticion.leidas == []


def test_un_content_length_mentiroso_no_engana() -> None:
    peticion = _peticion([b"a" * 80, b"b" * 80], {"content-length": "10"})
    with pytest.raises(CuerpoDemasiadoGrande):
        asyncio.run(leer_cuerpo_limitado(peticion, 100))


def test_justo_en_el_limite_se_acepta() -> None:
    peticion = _peticion([b"a" * 50, b"b" * 50])
    assert asyncio.run(leer_cuerpo_limitado(peticion, 100)) == b"a" * 50 + b"b" * 50
