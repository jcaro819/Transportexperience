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

from app.comun.errores import registrar_manejadores
from app.db import obtener_sesion
from app.modulos.inventario.rutas import enrutador_catalogo, enrutador_vehiculos
from app.modulos.portal.rutas import enrutador_portal
from app.modulos.usuarios.rutas import enrutador_autenticacion, enrutador_usuarios

DESCRIPCION = """
Backend del MVP de TransportExperience: alquiler, venta y domicilio de ciclas, patines y
monopatines eléctricos.

**Autenticación.** `POST /autenticacion/token` con un formulario `username` (el correo) y
`password`. Envía el `access_token` recibido en el encabezado `Authorization: Bearer <token>`.
En esta página, usa el botón **Authorize**.

**Errores.** Todas las respuestas de error tienen la forma
`{"error": {"codigo", "mensaje", "accion", "detalles"}}`. Decide por `codigo`; muestra
`mensaje` y `accion` al usuario.

**Listas.** Siempre paginadas: parámetros `pagina` (desde 1) y `tamano` (máx. 100).
"""

app = FastAPI(title="TransportExperience API", version="0.1.0", description=DESCRIPCION)
registrar_manejadores(app)
app.include_router(enrutador_autenticacion)
app.include_router(enrutador_usuarios)
app.include_router(enrutador_catalogo)
app.include_router(enrutador_vehiculos)
app.include_router(enrutador_portal)


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
