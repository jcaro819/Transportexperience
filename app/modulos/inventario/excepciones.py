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
