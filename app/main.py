"""Punto de entrada de la API de TransportExperience.

Arranque en desarrollo:  uvicorn app.main:app --reload
Documentación interactiva: http://127.0.0.1:8000/docs
"""

from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import obtener_sesion

app = FastAPI(
    title="TransportExperience API",
    version="0.1.0",
    description=(
        "Backend del MVP de TransportExperience: alquiler, venta y domicilio de "
        "ciclas, patines y monopatines eléctricos."
    ),
)


class EstadoSalud(BaseModel):
    """Respuesta del chequeo de salud."""

    estado: Literal["ok", "degradado"]
    base_datos: Literal["ok", "sin_conexion"]


@app.get(
    "/salud",
    response_model=EstadoSalud,
    tags=["sistema"],
    summary="Chequeo de salud",
    responses={503: {"model": EstadoSalud, "description": "La base de datos no responde"}},
)
def salud(respuesta: Response, sesion: Annotated[Session, Depends(obtener_sesion)]) -> EstadoSalud:
    """Indica si la API está viva y si alcanza la base de datos."""
    try:
        sesion.execute(text("SELECT 1"))
    except SQLAlchemyError:
        respuesta.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return EstadoSalud(estado="degradado", base_datos="sin_conexion")
    return EstadoSalud(estado="ok", base_datos="ok")
