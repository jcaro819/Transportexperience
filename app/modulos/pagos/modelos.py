"""Modelos del módulo de pagos (HU-05).

Reglas que el modelo hace cumplir por sí mismo (CLAUDE.md 7.3):

- Montos en pesos enteros.
- Cada pago cobra exactamente un alquiler o una venta, con el envío ya incluido en su total.
- No puede haber dos cobros aprobados de lo mismo (índices únicos parciales).
- Un pago aprobado no se edita: se compensa con otro registro que lo referencia.
- Cada webhook se guarda crudo, y los repetidos se descartan por ``clave_idempotencia``.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    false,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.comun.modelos import ConMarcasDeTiempo, Dinero, tipo_estado
from app.db import Base


class EstadoPago(StrEnum):
    PENDIENTE = "pendiente"
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"
    EXPIRADO = "expirado"
    ERROR = "error"


class TipoPago(StrEnum):
    COBRO = "cobro"
    COMPENSACION = "compensacion"  # reverso o ajuste de un pago aprobado


class MetodoPago(ConMarcasDeTiempo, Base):
    """Tarjeta, PSE... El administrador los habilita o deshabilita (SRS 3.5.3)."""

    __tablename__ = "metodos_pago"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(60))
    activo: Mapped[bool] = mapped_column(default=True, server_default=true())


_COBRO_APROBADO = "estado = 'aprobado' AND tipo = 'cobro'"


class Pago(ConMarcasDeTiempo, Base):
    __tablename__ = "pagos"
    __table_args__ = (
        CheckConstraint("num_nonnulls(alquiler_id, venta_id) = 1", name="una_sola_operacion"),
        CheckConstraint("monto > 0", name="monto_positivo"),
        CheckConstraint(
            "(tipo = 'compensacion') = (pago_compensado_id IS NOT NULL)",
            name="compensacion_referencia_pago",
        ),
        CheckConstraint(
            "(estado = 'aprobado') = (aprobado_en IS NOT NULL)", name="fecha_aprobacion"
        ),
        # Nunca dos cobros aprobados de la misma operación (SRS 3.3.3).
        Index(
            "uq_pagos_alquiler_cobro_aprobado",
            "alquiler_id",
            unique=True,
            postgresql_where=_COBRO_APROBADO,
        ),
        Index(
            "uq_pagos_venta_cobro_aprobado",
            "venta_id",
            unique=True,
            postgresql_where=_COBRO_APROBADO,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Referencia nuestra que viaja a la pasarela y vuelve en el webhook.
    referencia: Mapped[str] = mapped_column(String(40), unique=True)
    tipo: Mapped[TipoPago] = mapped_column(
        tipo_estado(TipoPago, "tipo_pago"),
        default=TipoPago.COBRO,
        server_default=TipoPago.COBRO.value,
    )
    alquiler_id: Mapped[int | None] = mapped_column(ForeignKey("alquileres.id"), index=True)
    venta_id: Mapped[int | None] = mapped_column(ForeignKey("ventas.id"), index=True)
    metodo_pago_id: Mapped[int] = mapped_column(ForeignKey("metodos_pago.id"))
    monto: Mapped[int] = mapped_column(Dinero)
    estado: Mapped[EstadoPago] = mapped_column(
        tipo_estado(EstadoPago, "estado_pago"),
        default=EstadoPago.PENDIENTE,
        server_default=EstadoPago.PENDIENTE.value,
        index=True,
    )
    proveedor: Mapped[str] = mapped_column(String(20))  # "wompi" o "falso"
    id_transaccion_pasarela: Mapped[str | None] = mapped_column(String(64), unique=True)
    pago_compensado_id: Mapped[int | None] = mapped_column(ForeignKey("pagos.id"))
    aprobado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detalle_error: Mapped[str | None] = mapped_column(Text)


class EventoPago(Base):
    """Webhook recibido de la pasarela, guardado tal cual llegó.

    ``clave_idempotencia`` = id de transacción + estado reportado. Solo se llena si la firma
    es válida, para que un evento falso no bloquee al verdadero.
    """

    __tablename__ = "eventos_pago"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    proveedor: Mapped[str] = mapped_column(String(20))
    clave_idempotencia: Mapped[str | None] = mapped_column(String(120), unique=True)
    pago_id: Mapped[int | None] = mapped_column(ForeignKey("pagos.id"), index=True)
    firma_valida: Mapped[bool] = mapped_column(Boolean)
    estado_reportado: Mapped[str | None] = mapped_column(String(30))
    cuerpo_crudo: Mapped[str] = mapped_column(Text)
    procesado: Mapped[bool] = mapped_column(default=False, server_default=false())
    error: Mapped[str | None] = mapped_column(Text)
    recibido_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
