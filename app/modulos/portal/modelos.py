"""Modelos del portal institucional (HU-01) y horarios de atención (SRS 3.5.3).

Ambos son editables por el administrador sin tocar código.
"""

from datetime import datetime, time
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, SmallInteger, String, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SeccionPortal(StrEnum):
    """Secciones del portal que pide HU-01, en el orden en que se muestran."""

    MISION = "mision"
    VISION = "vision"
    CONTACTO = "contacto"


class DiaSemana(StrEnum):
    """Días en el orden de ``horarios_atencion.dia_semana`` (0 = lunes ... 6 = domingo)."""

    LUNES = "lunes"
    MARTES = "martes"
    MIERCOLES = "miercoles"
    JUEVES = "jueves"
    VIERNES = "viernes"
    SABADO = "sabado"
    DOMINGO = "domingo"

    @property
    def numero(self) -> int:
        return list(DiaSemana).index(self)


class ContenidoPortal(Base):
    """Texto de una sección del portal: misión, visión, contacto..."""

    __tablename__ = "contenido_portal"

    id: Mapped[int] = mapped_column(primary_key=True)
    seccion: Mapped[str] = mapped_column(String(30), unique=True)
    titulo: Mapped[str] = mapped_column(String(120))
    contenido: Mapped[str] = mapped_column(Text)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class HorarioAtencion(Base):
    """Horario de un día de la semana (0 = lunes ... 6 = domingo). Sin fila = cerrado."""

    __tablename__ = "horarios_atencion"
    __table_args__ = (
        CheckConstraint("dia_semana BETWEEN 0 AND 6", name="dia_semana_rango"),
        CheckConstraint("hora_cierre > hora_apertura", name="horas_ordenadas"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dia_semana: Mapped[int] = mapped_column(SmallInteger, unique=True)
    hora_apertura: Mapped[time] = mapped_column(Time)
    hora_cierre: Mapped[time] = mapped_column(Time)
