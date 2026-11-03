"""Lectura segura del cuerpo de una petición (requisito no funcional del Sprint 4).

``await request.body()`` lee el cuerpo entero a memoria antes de que podamos medirlo: un
cuerpo enorme (por error o a propósito) la llenaría. Aquí se lee por partes y se corta en
cuanto pasa del límite, sin esperar al final.
"""

from fastapi import Request, status

from app.comun.errores import ErrorDeNegocio


class CuerpoDemasiadoGrande(ErrorDeNegocio):
    codigo = "cuerpo_demasiado_grande"
    mensaje = "El cuerpo de la solicitud es demasiado grande."
    accion = "Envía un cuerpo más pequeño."
    estado_http = status.HTTP_413_CONTENT_TOO_LARGE


async def leer_cuerpo_limitado(request: Request, limite: int) -> bytes:
    """El cuerpo completo, o ``CuerpoDemasiadoGrande`` si pasa de ``limite`` bytes.

    Primero mira ``Content-Length`` (rechazo inmediato, sin leer nada) y luego cuenta lo que
    de verdad llega, porque ese encabezado puede faltar (envío por partes) o mentir.
    """
    declarado = request.headers.get("content-length", "")
    if declarado.isdigit() and int(declarado) > limite:
        raise CuerpoDemasiadoGrande(f"El cuerpo supera el máximo de {limite} bytes.")
    partes: list[bytes] = []
    total = 0
    async for parte in request.stream():
        total += len(parte)
        if total > limite:
            raise CuerpoDemasiadoGrande(f"El cuerpo supera el máximo de {limite} bytes.")
        partes.append(parte)
    return b"".join(partes)
