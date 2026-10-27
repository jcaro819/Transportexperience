"""Errores de negocio de los domicilios (HU-06). Cada uno dice la causa y qué hacer."""

from fastapi import status

from app.comun.errores import ErrorDeNegocio


class FueraDeCobertura(ErrorDeNegocio):
    codigo = "fuera_de_cobertura"
    mensaje = "Esa dirección está fuera de nuestras zonas de entrega."
    accion = "Marca en el mapa un punto dentro de una zona de cobertura, o recoge en el local."
    estado_http = status.HTTP_422_UNPROCESSABLE_CONTENT


class DomicilioNoEncontrado(ErrorDeNegocio):
    codigo = "domicilio_no_encontrado"
    mensaje = "No encontramos ese domicilio."
    accion = "Revisa la lista de tus domicilios."
    estado_http = status.HTTP_404_NOT_FOUND


class YaTieneDomicilio(ErrorDeNegocio):
    codigo = "ya_tiene_domicilio"
    mensaje = "Esta operación ya tiene un domicilio."
    accion = "Para cambiar la dirección, cancela el domicilio actual y solicita uno nuevo."
    estado_http = status.HTTP_409_CONFLICT


class OperacionNoAdmiteDomicilio(ErrorDeNegocio):
    codigo = "operacion_no_admite_domicilio"
    mensaje = "El domicilio solo se agrega o se quita antes de pagar."
    accion = "Solicita el domicilio mientras la reserva o la compra está pendiente de pago."
    estado_http = status.HTTP_409_CONFLICT


class TransicionDeDomicilioInvalida(ErrorDeNegocio):
    codigo = "transicion_de_domicilio_invalida"
    mensaje = "El domicilio no puede pasar a ese estado desde su estado actual."
    accion = "Consulta el domicilio para ver su estado actual."
    estado_http = status.HTTP_409_CONFLICT


class DomicilioSinPagar(ErrorDeNegocio):
    codigo = "domicilio_sin_pagar"
    mensaje = "Este domicilio todavía no se puede asignar: la operación no está pagada."
    accion = "Espera a que el cliente pague y vuelve a intentarlo."
    estado_http = status.HTTP_409_CONFLICT


class DomiciliarioNoDisponible(ErrorDeNegocio):
    codigo = "domiciliario_no_disponible"
    mensaje = "Ese domiciliario no está disponible."
    accion = "Elige uno de la lista de domiciliarios disponibles."
    estado_http = status.HTTP_409_CONFLICT


class VehiculoDeTransporteNoDisponible(ErrorDeNegocio):
    codigo = "vehiculo_de_transporte_no_disponible"
    mensaje = "Esa unidad no se puede usar para la entrega."
    accion = "Elige una unidad disponible hoy, o asigna el domicilio sin vehículo."
    estado_http = status.HTTP_409_CONFLICT
