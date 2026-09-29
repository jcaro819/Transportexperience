"""Reglas de negocio de alquileres (HU-03).

Por ahora solo la consulta de ocupación, que usa también el catálogo (HU-02). La creación
de reservas llega con HU-03.
"""

from datetime import date, datetime

from sqlalchemy import Select, func, literal_column, or_, select

from app.modulos.alquileres.modelos import ESTADOS_ACTIVOS, Alquiler, EstadoAlquiler

# Mismo texto de la restricción de exclusión, para que Postgres pueda usar su índice GiST.
_RANGO_ALQUILER = func.daterange(Alquiler.fecha_inicio, Alquiler.fecha_fin, literal_column("'[]'"))


def consulta_vehiculos_ocupados(inicio: date, fin: date, momento: datetime) -> Select:
    """Ids de los vehículos con un alquiler activo que se cruza con [inicio, fin].

    Fechas inclusivas, como en la restricción de exclusión. Un ``pendiente_pago`` cuyo
    ``expira_en`` ya pasó no ocupa el vehículo aunque todavía no se haya marcado como
    ``expirado`` (eso lo hace quien crea una reserva, CLAUDE.md 7.1 regla 2): una consulta
    de lectura no debe escribir, pero tampoco debe mostrar ocupado lo que ya se liberó.
    """
    pedido = func.daterange(inicio, fin, literal_column("'[]'"))
    return select(Alquiler.vehiculo_id).where(
        Alquiler.estado.in_(ESTADOS_ACTIVOS),
        or_(Alquiler.estado != EstadoAlquiler.PENDIENTE_PAGO, Alquiler.expira_en > momento),
        _RANGO_ALQUILER.op("&&")(pedido),
    )


def consulta_alquileres_vigentes(vehiculo_id: int, desde: date, momento: datetime) -> Select:
    """Alquileres activos del vehículo que terminan ``desde`` en adelante (en curso o futuros).

    Igual que arriba, un ``pendiente_pago`` vencido no cuenta.
    """
    return (
        select(Alquiler)
        .where(
            Alquiler.vehiculo_id == vehiculo_id,
            Alquiler.estado.in_(ESTADOS_ACTIVOS),
            or_(Alquiler.estado != EstadoAlquiler.PENDIENTE_PAGO, Alquiler.expira_en > momento),
            Alquiler.fecha_fin >= desde,
        )
        .order_by(Alquiler.fecha_inicio)
    )


def consulta_alquiler_en_curso(vehiculo_id: int) -> Select:
    """El alquiler que el cliente tiene en sus manos ahora mismo, si existe."""
    return select(Alquiler.id).where(
        Alquiler.vehiculo_id == vehiculo_id, Alquiler.estado == EstadoAlquiler.EN_CURSO
    )
