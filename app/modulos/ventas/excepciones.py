"""Errores de negocio de las ventas (HU-04). Cada uno dice la causa y qué hacer."""

from fastapi import status

from app.comun.errores import ErrorDeNegocio


class VentaNoEncontrada(ErrorDeNegocio):
    codigo = "venta_no_encontrada"
    mensaje = "No encontramos esa compra."
    accion = "Revisa la lista de tus compras."
    estado_http = status.HTTP_404_NOT_FOUND


class ProductoNoEncontrado(ErrorDeNegocio):
    codigo = "producto_no_encontrado"
    mensaje = "Ese accesorio o repuesto no existe o ya no está a la venta."
    accion = "Vuelve al listado de accesorios y repuestos y elige otro."
    estado_http = status.HTTP_404_NOT_FOUND


class ModeloNoSeVende(ErrorDeNegocio):
    codigo = "modelo_no_se_vende"
    mensaje = "Este vehículo solo se alquila, no está a la venta."
    accion = "Elige un vehículo con precio de venta o revisa la opción de alquiler."
    estado_http = status.HTTP_409_CONFLICT


class SinUnidadesParaVenta(ErrorDeNegocio):
    codigo = "sin_unidades_para_venta"
    mensaje = "No hay suficientes unidades de este vehículo disponibles para la venta."
    accion = "Reduce la cantidad o elige otro vehículo."
    estado_http = status.HTTP_409_CONFLICT


class StockInsuficiente(ErrorDeNegocio):
    codigo = "stock_insuficiente"
    mensaje = "No hay suficiente stock de este producto."
    accion = "Reduce la cantidad o elige otro producto."
    estado_http = status.HTTP_409_CONFLICT


class TransicionDeVentaInvalida(ErrorDeNegocio):
    codigo = "transicion_de_venta_invalida"
    mensaje = "La compra no puede pasar a ese estado desde su estado actual."
    accion = "Consulta la compra para ver su estado actual."
    estado_http = status.HTTP_409_CONFLICT


class VentaExpirada(ErrorDeNegocio):
    codigo = "venta_expirada"
    mensaje = "La compra expiró porque no se pagó dentro de los 15 minutos del bloqueo."
    accion = "Vuelve a hacer la compra: los productos quedaron libres para cualquier cliente."
    estado_http = status.HTTP_409_CONFLICT


class VentaNoCancelable(ErrorDeNegocio):
    codigo = "venta_no_cancelable"
    mensaje = "Esta compra ya no se puede cancelar desde la aplicación."
    accion = (
        "Solo se cancelan compras pendientes de pago. Si ya pagaste, comunícate con "
        "TransportExperience."
    )
    estado_http = status.HTTP_409_CONFLICT
