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


class PagoNoEncontrado(ErrorDeNegocio):
    codigo = "pago_no_encontrado"
    mensaje = "No encontramos ese pago."
    accion = "Revisa la referencia del pago en tu alquiler o tu compra."
    estado_http = status.HTTP_404_NOT_FOUND


class PagoEnCurso(ErrorDeNegocio):
    codigo = "pago_en_curso"
    mensaje = "Ya hay un pago en proceso para esta operación."
    accion = "Espera a que el banco lo confirme o lo rechace; consulta el estado del pago."
    estado_http = status.HTTP_409_CONFLICT


class DatosDePagoIncompletos(ErrorDeNegocio):
    codigo = "datos_de_pago_incompletos"
    mensaje = "Faltan los datos del método de pago."
    accion = "Con tarjeta envía `tarjeta.token`; con PSE envía los datos de `pse`."
    estado_http = status.HTTP_422_UNPROCESSABLE_CONTENT


class TerminosNoAceptados(ErrorDeNegocio):
    codigo = "terminos_no_aceptados"
    mensaje = "Para pagar debes aceptar los términos y la autorización de datos de la pasarela."
    accion = "Muestra los enlaces de `/pagos/configuracion` y envía `acepta_terminos: true`."
    estado_http = status.HTTP_422_UNPROCESSABLE_CONTENT


class DevolucionNoPendiente(ErrorDeNegocio):
    codigo = "devolucion_no_pendiente"
    mensaje = "Ese pago no es una devolución pendiente."
    accion = "Revisa la lista de devoluciones pendientes."
    estado_http = status.HTTP_409_CONFLICT
