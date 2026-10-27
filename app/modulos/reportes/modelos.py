"""Modelos del módulo de reportes (HU-11).

Los reportes agregados (ingresos, vehículos más usados...) son consultas y no tienen
tabla. Lo que sí se guarda son las actas de entrega y recepción, que certifican en qué
estado estaba el vehículo, con el registro de conformidad propuesto para la "firma
digital" del plan (usuario, fecha y hash del PDF). *Pendiente de confirmar con el equipo.*
"""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.comun.modelos import tipo_estado
from app.db import Base

if TYPE_CHECKING:
    from app.modulos.alquileres.modelos import Alquiler
    from app.modulos.inventario.modelos import Vehiculo
    from app.modulos.usuarios.modelos import Usuario
    from app.modulos.ventas.modelos import Venta


class TipoActa(StrEnum):
    ENTREGA = "entrega"  # el vehículo sale hacia el cliente
    RECEPCION = "recepcion"  # el vehículo vuelve (fin del alquiler)


class Acta(Base):
    __tablename__ = "actas"
    __table_args__ = (
        CheckConstraint("num_nonnulls(alquiler_id, venta_id) = 1", name="acta_de_alquiler_o_venta"),
        CheckConstraint("nivel_bateria BETWEEN 0 AND 100", name="nivel_bateria_rango"),
        CheckConstraint(
            "num_nonnulls(conforme_por_id, conforme_en, hash_pdf) IN (0, 3)",
            name="conformidad_completa",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[TipoActa] = mapped_column(tipo_estado(TipoActa, "tipo_acta"))
    vehiculo_id: Mapped[int] = mapped_column(ForeignKey("vehiculos.id"), index=True)
    alquiler_id: Mapped[int | None] = mapped_column(ForeignKey("alquileres.id"), index=True)
    venta_id: Mapped[int | None] = mapped_column(ForeignKey("ventas.id"), index=True)
    domicilio_id: Mapped[int | None] = mapped_column(ForeignKey("domicilios.id"))
    estado_vehiculo: Mapped[str] = mapped_column(Text)
    nivel_bateria: Mapped[int | None] = mapped_column(SmallInteger)
    registrada_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Conformidad: quién la dio, cuándo y el SHA-256 del PDF que aceptó.
    conforme_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    conforme_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hash_pdf: Mapped[str | None] = mapped_column(String(64))

    vehiculo: Mapped["Vehiculo"] = relationship()
    alquiler: Mapped["Alquiler | None"] = relationship()
    venta: Mapped["Venta | None"] = relationship()
    registrada_por: Mapped["Usuario"] = relationship(foreign_keys=[registrada_por_id])
    conforme_por: Mapped["Usuario | None"] = relationship(foreign_keys=[conforme_por_id])

    @property
    def numero(self) -> str:
        return f"ACT-{self.id:06d}"

    @property
    def cliente_id(self) -> int:
        """El cliente de la operación: el dueño del alquiler o de la compra."""
        return self.alquiler.cliente_id if self.alquiler else self.venta.cliente_id
