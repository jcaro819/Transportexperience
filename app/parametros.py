"""Parámetros de negocio editables en base de datos (SRS 3.5.3).

Reglas numéricas que el administrador puede cambiar sin tocar código, como el máximo de
días de un alquiler. Cada parámetro es una fila ``clave -> valor``; los valores iniciales
los crea la migración que agrega el parámetro, así la fila siempre existe.

En el código solo va el *nombre* del parámetro (``MAX_DIAS_ALQUILER``), nunca su valor.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base

# Claves conocidas. El valor vive en la tabla ``parametros_sistema``.
MAX_DIAS_ALQUILER = "max_dias_alquiler"
MAX_MINUTOS_PAGO_PENDIENTE = "max_minutos_pago_pendiente"


class ParametroSistema(Base):
    """Un parámetro de negocio con valor entero, editable por el administrador."""

    __tablename__ = "parametros_sistema"

    clave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[int] = mapped_column(Integer)
    descripcion: Mapped[str] = mapped_column(Text)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ParametroFaltante(RuntimeError):
    """La fila del parámetro no existe: falta aplicar una migración (``alembic upgrade head``)."""


def obtener_entero(sesion: Session, clave: str) -> int:
    """Valor actual del parámetro ``clave``. Se lee en cada operación: un cambio aplica ya."""
    parametro = sesion.get(ParametroSistema, clave)
    if parametro is None:
        raise ParametroFaltante(
            f"Falta el parámetro '{clave}' en parametros_sistema. Ejecuta: alembic upgrade head"
        )
    return parametro.valor
