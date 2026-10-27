"""Consultas de solo lectura sobre los domicilios que usan otros módulos (HU-06, HU-09).

Viven aparte del servicio para que inventario pueda importarlas sin crear un import
circular, igual que ``alquileres/consultas.py``.
"""

from sqlalchemy import Select, or_, select

from app.modulos.alquileres.modelos import Alquiler
from app.modulos.domicilios.modelos import Domicilio, EstadoDomicilio

ESTADOS_FINALES = (EstadoDomicilio.ENTREGADO, EstadoDomicilio.CANCELADO)
# El domiciliario ya tiene el pedido: asignado, recogido o en camino.
ESTADOS_EN_RUTA = (EstadoDomicilio.ASIGNADO, EstadoDomicilio.RECOGIDO, EstadoDomicilio.EN_CAMINO)


def consulta_domicilios_sin_finalizar(vehiculo_id: int) -> Select:
    """Domicilios sin terminar en los que participa la unidad.

    Participa si es el vehículo que usa el domiciliario, o si es la unidad alquilada que
    se está entregando.
    """
    alquileres_de_la_unidad = select(Alquiler.id).where(Alquiler.vehiculo_id == vehiculo_id)
    return select(Domicilio.id).where(
        Domicilio.estado.not_in(ESTADOS_FINALES),
        or_(
            Domicilio.vehiculo_transporte_id == vehiculo_id,
            Domicilio.alquiler_id.in_(alquileres_de_la_unidad),
        ),
    )


def consulta_vehiculo_en_ruta_de(domiciliario_id: int, vehiculo_id: int) -> Select:
    """El domicilio en ruta en el que ``domiciliario_id`` usa ``vehiculo_id``, si existe.

    Así el domiciliario solo reporta novedades del vehículo que lleva (no ve la flota).
    """
    return select(Domicilio.id).where(
        Domicilio.domiciliario_id == domiciliario_id,
        Domicilio.vehiculo_transporte_id == vehiculo_id,
        Domicilio.estado.in_(ESTADOS_EN_RUTA),
    )
