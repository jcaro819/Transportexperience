"""Piezas compartidas por los modelos de todos los módulos.

- El dinero es siempre un entero en pesos colombianos (``BigInteger``). Nunca ``float``.
- Las fechas y horas se guardan con zona horaria (``timestamptz``).
- Los estados se guardan como texto con una restricción CHECK, no como ENUM nativo de
  Postgres: agregar un estado nuevo después es una migración trivial.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, Enum, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

# Pesos colombianos enteros. Un alias para que el tipo se lea igual en todo el código.
Dinero = BigInteger

# Grados decimales con 6 decimales: ~11 cm de resolución, suficiente para HU-08 (< 10 m).
Coordenada = Numeric(9, 6)


def tipo_estado(enumeracion: type[StrEnum], nombre: str) -> Enum:
    """Columna de texto restringida a los valores de ``enumeracion`` (CHECK en la base)."""
    return Enum(
        enumeracion,
        name=nombre,
        native_enum=False,
        create_constraint=True,
        length=30,
        values_callable=lambda miembros: [m.value for m in miembros],
        validate_strings=True,
    )


class ConMarcasDeTiempo:
    """Agrega ``creado_en`` y ``actualizado_en``, llenados por la base."""

    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
