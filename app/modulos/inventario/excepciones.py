"""Errores de negocio del inventario y el catálogo. Cada uno dice la causa y qué hacer."""

from fastapi import status

from app.comun.errores import ErrorDeNegocio


class ModeloNoEncontrado(ErrorDeNegocio):
    codigo = "modelo_no_encontrado"
    mensaje = "Ese vehículo no existe o ya no está en el catálogo."
    accion = "Vuelve al catálogo y elige otro vehículo."
    estado_http = status.HTTP_404_NOT_FOUND


class ModeloNoSeAlquila(ErrorDeNegocio):
    codigo = "modelo_no_se_alquila"
    mensaje = "Este vehículo solo está a la venta, no se alquila."
    accion = "Elige un vehículo con tarifa diaria o revisa la opción de compra."
    estado_http = status.HTTP_409_CONFLICT


class RangoDeTarifaInvalido(ErrorDeNegocio):
    codigo = "rango_de_tarifa_invalido"
    mensaje = "La tarifa mínima es mayor que la tarifa máxima."
    accion = "Ajusta el rango de tarifa del filtro."
    estado_http = status.HTTP_422_UNPROCESSABLE_CONTENT


class FechasInvalidas(ErrorDeNegocio):
    codigo = "fechas_invalidas"
    mensaje = "Las fechas no son válidas."
    accion = "Elige una fecha de inicio desde hoy y una fecha de fin igual o posterior."
    estado_http = status.HTTP_422_UNPROCESSABLE_CONTENT


class VehiculoNoEncontrado(ErrorDeNegocio):
    codigo = "vehiculo_no_encontrado"
    mensaje = "No existe una unidad con ese identificador."
    accion = "Verifica el identificador o busca la unidad en la lista de la flota."
    estado_http = status.HTTP_404_NOT_FOUND


class NovedadNoEncontrada(ErrorDeNegocio):
    codigo = "novedad_no_encontrada"
    mensaje = "Esa novedad no existe o no pertenece a esta unidad."
    accion = "Revisa el historial de novedades de la unidad."
    estado_http = status.HTTP_404_NOT_FOUND


class NovedadYaCerrada(ErrorDeNegocio):
    codigo = "novedad_ya_cerrada"
    mensaje = "Esa novedad ya estaba cerrada."
    accion = "Revisa el historial de novedades de la unidad."
    estado_http = status.HTTP_409_CONFLICT


class TransicionInvalida(ErrorDeNegocio):
    codigo = "transicion_invalida"
    mensaje = "La unidad no puede pasar a ese estado desde su estado actual."
    accion = "Revisa el estado actual de la unidad antes de cambiarlo."
    estado_http = status.HTTP_409_CONFLICT


class VehiculoVendido(ErrorDeNegocio):
    codigo = "vehiculo_vendido"
    mensaje = "Esta unidad ya fue vendida y no forma parte de la flota."
    accion = "Elige otra unidad."
    estado_http = status.HTTP_409_CONFLICT


class NoPuedeVolverAServicio(ErrorDeNegocio):
    codigo = "no_puede_volver_a_servicio"
    mensaje = "La unidad no puede volver a servicio todavía."
    accion = "Resuelve lo que la tiene ocupada y vuelve a intentarlo."
    estado_http = status.HTTP_409_CONFLICT
