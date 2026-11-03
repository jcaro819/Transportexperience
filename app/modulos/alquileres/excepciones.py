"""Errores de negocio de los alquileres (HU-03). Cada uno dice la causa y qué hacer."""

from fastapi import status

from app.comun.errores import ErrorDeNegocio


class AlquilerNoEncontrado(ErrorDeNegocio):
    codigo = "alquiler_no_encontrado"
    mensaje = "No encontramos ese alquiler."
    accion = "Revisa la lista de tus alquileres."
    estado_http = status.HTTP_404_NOT_FOUND


class DuracionExcedida(ErrorDeNegocio):
    codigo = "duracion_excedida"
    mensaje = "El alquiler supera el máximo de días permitido."
    accion = "Elige un rango de fechas más corto."
    estado_http = status.HTTP_422_UNPROCESSABLE_CONTENT


class SinUnidadesDisponibles(ErrorDeNegocio):
    codigo = "sin_unidades_disponibles"
    mensaje = "No hay unidades libres de este vehículo en esas fechas."
    accion = "Prueba con otras fechas o con otro vehículo del catálogo."
    estado_http = status.HTTP_409_CONFLICT


class TransicionDeAlquilerInvalida(ErrorDeNegocio):
    codigo = "transicion_de_alquiler_invalida"
    mensaje = "El alquiler no puede pasar a ese estado desde su estado actual."
    accion = "Consulta el alquiler para ver su estado actual."
    estado_http = status.HTTP_409_CONFLICT


class ReservaExpirada(ErrorDeNegocio):
    codigo = "reserva_expirada"
    mensaje = "La reserva expiró porque no se pagó dentro de los 15 minutos del bloqueo."
    accion = "Vuelve a reservar: el vehículo quedó libre para cualquier cliente."
    estado_http = status.HTTP_409_CONFLICT


class AlquilerNoCancelable(ErrorDeNegocio):
    codigo = "alquiler_no_cancelable"
    mensaje = "Este alquiler ya no se puede cancelar desde la aplicación."
    accion = (
        "Solo se cancelan reservas pendientes de pago. Si ya pagaste, comunícate con "
        "TransportExperience para gestionar la devolución."
    )
    estado_http = status.HTTP_409_CONFLICT


class FueraDeLasFechasDelAlquiler(ErrorDeNegocio):
    codigo = "fuera_de_las_fechas_del_alquiler"
    mensaje = "Hoy no está dentro de las fechas del alquiler."
    accion = "Entrega el vehículo entre la fecha de inicio y la de fin del alquiler."
    estado_http = status.HTTP_409_CONFLICT


class VehiculoNoListoParaEntrega(ErrorDeNegocio):
    codigo = "vehiculo_no_listo_para_entrega"
    mensaje = "La unidad del alquiler no se puede entregar ahora."
    accion = "Revisa el estado de la unidad o reasigna el alquiler a otra."
    estado_http = status.HTTP_409_CONFLICT


class ReasignacionInvalida(ErrorDeNegocio):
    codigo = "reasignacion_invalida"
    mensaje = "No se puede mover el alquiler a esa unidad."
    accion = "Elige otra unidad libre del mismo modelo, o deja que el sistema escoja una."
    estado_http = status.HTTP_409_CONFLICT
