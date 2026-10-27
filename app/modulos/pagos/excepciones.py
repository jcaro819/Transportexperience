"""Errores de negocio de los pagos. Cada uno dice la causa y qué hacer."""

from fastapi import status

from app.comun.errores import ErrorDeNegocio


class MetodoDePagoNoDisponible(ErrorDeNegocio):
    codigo = "metodo_de_pago_no_disponible"
    mensaje = "Ese método de pago no existe o está deshabilitado."
    accion = "Elige otro método de pago, por ejemplo tarjeta o PSE."
    estado_http = status.HTTP_422_UNPROCESSABLE_CONTENT


class PasarelaNoDisponible(ErrorDeNegocio):
    codigo = "pasarela_no_disponible"
    mensaje = "La pasarela de pagos no está disponible en este momento. No se cobró nada."
    accion = "Inténtalo de nuevo en unos minutos."
    estado_http = status.HTTP_503_SERVICE_UNAVAILABLE
