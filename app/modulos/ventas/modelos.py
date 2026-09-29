"""Modelos del módulo de ventas (HU-04).

Una venta es el carrito ya confirmado: uno o varios ítems, cada uno es un vehículo
(unidad única, cantidad 1) o un producto (con cantidad). El stock se descuenta al crear la
venta y se devuelve si el pago no llega dentro del bloqueo de 15 minutos.

Si el cliente pide domicilio, el valor del envío va en ``valor_envio`` y un solo pago
cubre el ``total`` (subtotal + envío).
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.comun.modelos import ConMarcasDeTiempo, Dinero, tipo_estado
from app.db import Base


class EstadoVenta(StrEnum):
    PENDIENTE_PAGO = "pendiente_pago"
    PAGADA = "pagada"
    CANCELADA = "cancelada"
    EXPIRADA = "expirada"


class Venta(ConMarcasDeTiempo, Base):
    __tablename__ = "ventas"
    __table_args__ = (
        CheckConstraint("subtotal >= 0", name="subtotal_no_negativo"),
        CheckConstraint("valor_envio >= 0", name="valor_envio_no_negativo"),
        CheckConstraint("total = subtotal + valor_envio", name="total_cuadra"),
        CheckConstraint(
            "(estado = 'pendiente_pago') = (expira_en IS NOT NULL)",
            name="expiracion_solo_pendiente",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    estado: Mapped[EstadoVenta] = mapped_column(
        tipo_estado(EstadoVenta, "estado_venta"), index=True
    )
    subtotal: Mapped[int] = mapped_column(Dinero)  # suma de los ítems
    # Copia de la tarifa de envío de la zona; 0 si no hay domicilio.
    valor_envio: Mapped[int] = mapped_column(Dinero, default=0, server_default="0")
    total: Mapped[int] = mapped_column(Dinero)
    expira_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list["ItemVenta"]] = relationship(
        back_populates="venta", cascade="all, delete-orphan"
    )


class ItemVenta(Base):
    """Línea de una venta. Guarda el precio del momento, no una referencia al actual."""

    __tablename__ = "items_venta"
    __table_args__ = (
        CheckConstraint("num_nonnulls(vehiculo_id, producto_id) = 1", name="vehiculo_o_producto"),
        CheckConstraint("vehiculo_id IS NULL OR cantidad = 1", name="vehiculo_cantidad_uno"),
        CheckConstraint("cantidad > 0", name="cantidad_positiva"),
        CheckConstraint("precio_unitario > 0", name="precio_unitario_positivo"),
        CheckConstraint("subtotal = cantidad * precio_unitario", name="subtotal_cuadra"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    venta_id: Mapped[int] = mapped_column(ForeignKey("ventas.id", ondelete="CASCADE"), index=True)
    vehiculo_id: Mapped[int | None] = mapped_column(ForeignKey("vehiculos.id"), index=True)
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("productos.id"), index=True)
    cantidad: Mapped[int]
    precio_unitario: Mapped[int] = mapped_column(Dinero)
    subtotal: Mapped[int] = mapped_column(Dinero)

    venta: Mapped[Venta] = relationship(back_populates="items")
