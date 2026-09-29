"""Errores con estructura uniforme para toda la API (SRS 3.2.3, CLAUDE.md sección 9).

Toda respuesta de error tiene la misma forma, sea un error de negocio, de validación o
de ruta inexistente::

    {"error": {"codigo": "correo_ya_registrado",
               "mensaje": "Ya existe una cuenta con ese correo.",
               "accion": "Inicia sesión o usa otro correo.",
               "detalles": null}}

El frontend decide por ``codigo`` y muestra ``mensaje`` y ``accion`` tal cual.
"""

import logging
from typing import Any, ClassVar

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

registro = logging.getLogger(__name__)


class DetalleCampo(BaseModel):
    campo: str
    mensaje: str


class CuerpoError(BaseModel):
    codigo: str
    mensaje: str
    accion: str
    detalles: list[DetalleCampo] | None = None


class ErrorRespuesta(BaseModel):
    """Forma de todas las respuestas de error de la API."""

    error: CuerpoError


class ErrorDeNegocio(Exception):
    """Base de los errores que el servicio lanza a propósito.

    Cada subclase fija ``codigo``, ``mensaje``, ``accion`` y ``estado_http``. Las rutas no
    los atrapan: el manejador global los convierte en la respuesta uniforme.
    """

    codigo: ClassVar[str] = "error"
    mensaje: ClassVar[str] = "No se pudo completar la operación."
    accion: ClassVar[str] = "Inténtalo de nuevo."
    estado_http: ClassVar[int] = status.HTTP_400_BAD_REQUEST
    encabezados: ClassVar[dict[str, str] | None] = None

    def __init__(self, mensaje: str | None = None) -> None:
        if mensaje is not None:
            self.mensaje = mensaje
        super().__init__(self.mensaje)


class NoAutenticado(ErrorDeNegocio):
    codigo = "no_autenticado"
    mensaje = "Debes iniciar sesión para hacer esto."
    accion = "Inicia sesión y vuelve a intentarlo."
    estado_http = status.HTTP_401_UNAUTHORIZED
    encabezados = {"WWW-Authenticate": "Bearer"}


class SesionExpirada(NoAutenticado):
    codigo = "sesion_expirada"
    mensaje = "Tu sesión expiró."
    accion = "Inicia sesión de nuevo."


class PermisoDenegado(ErrorDeNegocio):
    codigo = "permiso_denegado"
    mensaje = "Tu rol no tiene permiso para hacer esto."
    accion = "Si crees que es un error, comunícate con un administrador."
    estado_http = status.HTTP_403_FORBIDDEN


def _respuesta(
    estado: int,
    codigo: str,
    mensaje: str,
    accion: str,
    detalles: list[dict[str, str]] | None = None,
    encabezados: dict[str, str] | None = None,
) -> JSONResponse:
    cuerpo = {"codigo": codigo, "mensaje": mensaje, "accion": accion, "detalles": detalles}
    return JSONResponse({"error": cuerpo}, status_code=estado, headers=encabezados)


def _campo(ubicacion: tuple[Any, ...]) -> str:
    """("body", "correo") -> "correo"; ("query", "tamano") -> "tamano"."""
    partes = [str(p) for p in ubicacion if p not in ("body", "query", "path", "header", "form")]
    return ".".join(partes) or "solicitud"


async def _manejar_error_de_negocio(_: Request, error: ErrorDeNegocio) -> JSONResponse:
    return _respuesta(
        error.estado_http, error.codigo, error.mensaje, error.accion, encabezados=error.encabezados
    )


async def _manejar_validacion(_: Request, error: RequestValidationError) -> JSONResponse:
    detalles = [{"campo": _campo(e["loc"]), "mensaje": e["msg"]} for e in error.errors()]
    return _respuesta(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "datos_invalidos",
        "Algunos datos no son válidos.",
        "Revisa los campos indicados y vuelve a intentarlo.",
        detalles,
    )


async def _manejar_http(_: Request, error: StarletteHTTPException) -> JSONResponse:
    mensajes = {
        404: ("recurso_no_encontrado", "La dirección solicitada no existe."),
        405: ("metodo_no_permitido", "Esta dirección no admite ese método."),
    }
    codigo, mensaje = mensajes.get(error.status_code, (f"http_{error.status_code}", error.detail))
    return _respuesta(
        error.status_code,
        codigo,
        str(mensaje),
        "Revisa la dirección y el método de la solicitud.",
        encabezados=getattr(error, "headers", None),
    )


async def _manejar_inesperado(_: Request, error: Exception) -> JSONResponse:
    registro.exception("Error no controlado", exc_info=error)
    return _respuesta(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "error_interno",
        "Ocurrió un error inesperado. No se hizo ningún cambio.",
        "Inténtalo de nuevo en unos minutos. Si persiste, avisa a soporte.",
    )


def registrar_manejadores(app: FastAPI) -> None:
    """Conecta los manejadores de error a la aplicación."""
    app.add_exception_handler(ErrorDeNegocio, _manejar_error_de_negocio)
    app.add_exception_handler(RequestValidationError, _manejar_validacion)
    app.add_exception_handler(StarletteHTTPException, _manejar_http)
    app.add_exception_handler(Exception, _manejar_inesperado)


def respuestas_error(*estados: int) -> dict[int | str, dict[str, Any]]:
    """Documenta en OpenAPI las respuestas de error de una ruta."""
    descripciones = {
        400: "Operación inválida",
        401: "No autenticado o sesión expirada",
        403: "El rol no tiene permiso",
        404: "No encontrado",
        409: "Conflicto con el estado actual",
        422: "Datos inválidos",
    }
    return {e: {"model": ErrorRespuesta, "description": descripciones[e]} for e in estados}
