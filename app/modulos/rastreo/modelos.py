"""Modelos del módulo de rastreo GPS (HU-08).

Cada fila es una posición reportada por el simulador o por un dispositivo real. La
consulta de "última posición de cada vehículo" usa el índice (vehiculo_id, registrado_en).
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.comun.modelos import Coordenada, tipo_estado
from app.db import Base


class FuenteGps(StrEnum):
    SIMULADOR = "simulador"
    DISPOSITIVO = "dispositivo"


class PosicionGps(Base):
    __tablename__ = "posiciones_gps"
    __table_args__ = (
        CheckConstraint("latitud BETWEEN -90 AND 90", name="latitud_rango"),
        CheckConstraint("longitud BETWEEN -180 AND 180", name="longitud_rango"),
        CheckConstraint("nivel_bateria BETWEEN 0 AND 100", name="nivel_bateria_rango"),
        CheckConstraint("precision_metros >= 0", name="precision_no_negativa"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    vehiculo_id: Mapped[int] = mapped_column(ForeignKey("vehiculos.id"))
    latitud: Mapped[Decimal] = mapped_column(Coordenada)
    longitud: Mapped[Decimal] = mapped_column(Coordenada)
    # Precisión reportada por el GPS; HU-08 exige < 10 m.
    precision_metros: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    velocidad_kmh: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    nivel_bateria: Mapped[int | None] = mapped_column(SmallInteger)
    fuente: Mapped[FuenteGps] = mapped_column(tipo_estado(FuenteGps, "fuente_gps"))
    # Hora en que el dispositivo tomó la posición vs. hora en que llegó al servidor.
    registrado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recibido_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# "Última posición de cada vehículo" (HU-08, consulta cada 5 s): el índice ya viene
# ordenado de la más reciente a la más antigua.
Index(
    "ix_posiciones_gps_vehiculo_registrado",
    PosicionGps.vehiculo_id,
    PosicionGps.registrado_en.desc(),
)
