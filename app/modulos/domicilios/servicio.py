"""Reglas de negocio de domicilios (HU-06, HU-07).

Por ahora solo la consulta que usa el inventario (HU-09) para saber si una unidad está
comprometida en una entrega. La solicitud de domicilios llega con HU-06.
"""

from sqlalchemy import Select, or_, select

from app.modulos.alquileres.modelos import Alquiler
from app.modulos.domicilios.modelos import Domicilio, EstadoDomicilio

ESTADOS_FINALES = (EstadoDomicilio.ENTREGADO, EstadoDomicilio.CANCELADO)


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
