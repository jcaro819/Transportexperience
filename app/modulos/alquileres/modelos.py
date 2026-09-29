"""Modelos del módulo de alquileres (HU-03).

El alquiler se cobra por día. ``fecha_inicio`` y ``fecha_fin`` son inclusivas: del 5 al 7
son 3 días, y el siguiente cliente puede recoger desde el día 8.

Si el cliente pide domicilio, el valor del envío va en ``valor_envio`` y un solo pago
cubre el ``total`` (subtotal + envío).

La garantía de que un vehículo no se reserve dos veces (SRS 3.3.3) la da la base de datos,
no Python: la restricción de exclusión ``ex_alquileres_sin_solapamiento`` rechaza dos
alquileres activos del mismo vehículo con rangos de fechas que se crucen, aunque lleguen
en el mismo milisegundo.
"""

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Text, func, literal_column
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.comun.modelos import ConMarcasDeTiempo, Dinero, tipo_estado
from app.db import Base


class EstadoAlquiler(StrEnum):
    PENDIENTE_PAGO = "pendiente_pago"  # bloqueo temporal de 15 min mientras se paga
    CONFIRMADO = "confirmado"  # pagado, aún no empieza
    EN_CURSO = "en_curso"  # el cliente tiene el vehículo
    FINALIZADO = "finalizado"
    CANCELADO = "cancelado"
    EXPIRADO = "expirado"  # no se pagó dentro del bloqueo


# Estados que ocupan el vehículo en sus fechas. Deben coincidir con el WHERE de abajo.
ESTADOS_ACTIVOS = (
    EstadoAlquiler.PENDIENTE_PAGO,
    EstadoAlquiler.CONFIRMADO,
    EstadoAlquiler.EN_CURSO,
)


class Alquiler(ConMarcasDeTiempo, Base):
    """Reserva de un vehículo por días."""

    __tablename__ = "alquileres"
    __table_args__ = (
        CheckConstraint("fecha_fin >= fecha_inicio", name="fechas_ordenadas"),
        CheckConstraint("tarifa_diaria > 0", name="tarifa_diaria_positiva"),
        CheckConstraint("valor_envio >= 0", name="valor_envio_no_negativo"),
        # Días inclusivos: (fin - inicio + 1). En Postgres, date - date da un entero.
        CheckConstraint(
            "subtotal = (fecha_fin - fecha_inicio + 1) * tarifa_diaria", name="subtotal_cuadra"
        ),
        CheckConstraint("total = subtotal + valor_envio", name="total_cuadra"),
        CheckConstraint(
            "(estado = 'pendiente_pago') = (expira_en IS NOT NULL)",
            name="expiracion_solo_pendiente",
        ),
        ExcludeConstraint(
            ("vehiculo_id", "="),
            (
                func.daterange(literal_column("fecha_inicio"), literal_column("fecha_fin"), "[]"),
                "&&",
            ),
            name="ex_alquileres_sin_solapamiento",
            using="gist",
            where="estado IN ('pendiente_pago', 'confirmado', 'en_curso')",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    vehiculo_id: Mapped[int] = mapped_column(ForeignKey("vehiculos.id"), index=True)
    fecha_inicio: Mapped[date] = mapped_column(Date)
    fecha_fin: Mapped[date] = mapped_column(Date)
    # Copia de la tarifa al momento de reservar: si el admin la cambia después,
    # los alquileres ya hechos no se alteran.
    tarifa_diaria: Mapped[int] = mapped_column(Dinero)
    subtotal: Mapped[int] = mapped_column(Dinero)
    # Copia de la tarifa de envío de la zona; 0 si no hay domicilio.
    valor_envio: Mapped[int] = mapped_column(Dinero, default=0, server_default="0")
    total: Mapped[int] = mapped_column(Dinero)
    estado: Mapped[EstadoAlquiler] = mapped_column(
        tipo_estado(EstadoAlquiler, "estado_alquiler"), index=True
    )
    expira_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_cancelacion: Mapped[str | None] = mapped_column(Text)
