"""Modelos del módulo de domicilios (HU-06, HU-07) y de zonas de cobertura (SRS 3.6.3).

Un domicilio es la entrega de un alquiler o de una venta, ligado siempre a exactamente
uno de los dos (no hay domicilios sueltos). Lo lleva un domiciliario, que opcionalmente usa
un vehículo de la flota (SRS 3.1.7); ese vehículo queda en ``asignado_a_domicilio``.

El valor del envío no se guarda aquí sino en el alquiler o la venta (``valor_envio``),
porque un solo pago cubre el total. Una dirección fuera de cobertura se bloquea
(SRS 3.6.1): por eso ``zona_id`` es obligatorio.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.comun.modelos import ConMarcasDeTiempo, Coordenada, Dinero, tipo_estado
from app.db import Base


class EstadoDomicilio(StrEnum):
    """Los seis estados del SRS 3.1.7, que cubren los tres de HU-07."""

    PENDIENTE = "pendiente"
    ASIGNADO = "asignado"
    RECOGIDO = "recogido"
    EN_CAMINO = "en_camino"
    ENTREGADO = "entregado"
    CANCELADO = "cancelado"


class ZonaCobertura(ConMarcasDeTiempo, Base):
    """Área donde se hacen entregas, con su tarifa de envío fija.

    ``poligono`` es un GeoJSON Polygon: ``{"type": "Polygon", "coordinates":
    [[[lng, lat], ...]]}``. El mismo formato lo dibuja el mapa del frontend sin conversión.
    """

    __tablename__ = "zonas_cobertura"
    __table_args__ = (CheckConstraint("tarifa_envio >= 0", name="tarifa_envio_no_negativa"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)
    poligono: Mapped[dict[str, Any]] = mapped_column(JSONB)
    tarifa_envio: Mapped[int] = mapped_column(Dinero)
    activa: Mapped[bool] = mapped_column(default=True, server_default=true())


_DOMICILIO_ACTIVO = "estado <> 'cancelado'"
_EN_RUTA = "estado IN ('asignado', 'recogido', 'en_camino')"


class Domicilio(ConMarcasDeTiempo, Base):
    __tablename__ = "domicilios"
    __table_args__ = (
        CheckConstraint("num_nonnulls(alquiler_id, venta_id) = 1", name="entrega_alquiler_o_venta"),
        CheckConstraint("latitud BETWEEN -90 AND 90", name="latitud_rango"),
        CheckConstraint("longitud BETWEEN -180 AND 180", name="longitud_rango"),
        CheckConstraint(
            "estado IN ('pendiente', 'cancelado') OR domiciliario_id IS NOT NULL",
            name="asignado_tiene_domiciliario",
        ),
        # Un solo domicilio vigente por alquiler o venta.
        Index(
            "uq_domicilios_alquiler_activo",
            "alquiler_id",
            unique=True,
            postgresql_where=_DOMICILIO_ACTIVO,
        ),
        Index(
            "uq_domicilios_venta_activo",
            "venta_id",
            unique=True,
            postgresql_where=_DOMICILIO_ACTIVO,
        ),
        # Un vehículo de la flota no puede estar en dos entregas en ruta (SRS 3.3.3).
        Index(
            "uq_domicilios_vehiculo_en_ruta",
            "vehiculo_transporte_id",
            unique=True,
            postgresql_where=_EN_RUTA,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Código corto que el cliente usa para seguir su pedido (HU-07).
    codigo_rastreo: Mapped[str] = mapped_column(String(12), unique=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    alquiler_id: Mapped[int | None] = mapped_column(ForeignKey("alquileres.id"))
    venta_id: Mapped[int | None] = mapped_column(ForeignKey("ventas.id"))
    zona_id: Mapped[int] = mapped_column(ForeignKey("zonas_cobertura.id"))
    direccion: Mapped[str] = mapped_column(String(200))
    indicaciones: Mapped[str | None] = mapped_column(String(200))
    latitud: Mapped[Decimal] = mapped_column(Coordenada)
    longitud: Mapped[Decimal] = mapped_column(Coordenada)
    estado: Mapped[EstadoDomicilio] = mapped_column(
        tipo_estado(EstadoDomicilio, "estado_domicilio"),
        default=EstadoDomicilio.PENDIENTE,
        server_default=EstadoDomicilio.PENDIENTE.value,
        index=True,
    )
    domiciliario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)
    vehiculo_transporte_id: Mapped[int | None] = mapped_column(ForeignKey("vehiculos.id"))
    entregado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_cancelacion: Mapped[str | None] = mapped_column(Text)


class HistorialEstadoDomicilio(Base):
    """Cada cambio de estado de un domicilio, con quién y cuándo (SRS 3.3.1, HU-07)."""

    __tablename__ = "historial_estados_domicilio"

    id: Mapped[int] = mapped_column(primary_key=True)
    domicilio_id: Mapped[int] = mapped_column(
        ForeignKey("domicilios.id", ondelete="CASCADE"), index=True
    )
    estado_anterior: Mapped[EstadoDomicilio | None] = mapped_column(
        tipo_estado(EstadoDomicilio, "estado_anterior")
    )
    estado_nuevo: Mapped[EstadoDomicilio] = mapped_column(
        tipo_estado(EstadoDomicilio, "estado_nuevo")
    )
    cambiado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    cambiado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
