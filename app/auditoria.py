"""Registro de auditoría transversal (SRS 3.5.4).

Guarda quién cambió qué y cuándo en inventario, tarifas, estados de vehículos,
cancelaciones y ajustes de pagos. Los servicios llaman a ``registrar_auditoria`` dentro
de la misma transacción del cambio.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base


class RegistroAuditoria(Base):
    __tablename__ = "auditoria"
    __table_args__ = (Index("ix_auditoria_entidad", "entidad", "entidad_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Nulo cuando el cambio lo hace el sistema (p. ej., una reserva que expira sola).
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)
    accion: Mapped[str] = mapped_column(String(30))  # crear, actualizar, cambiar_estado...
    entidad: Mapped[str] = mapped_column(String(60))  # nombre de la tabla
    entidad_id: Mapped[str] = mapped_column(String(40))
    datos_anteriores: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    datos_nuevos: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ocurrido_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


def registrar_auditoria(
    sesion: Session,
    *,
    usuario_id: int | None,
    accion: str,
    entidad: str,
    entidad_id: int | str,
    antes: dict[str, Any] | None = None,
    despues: dict[str, Any] | None = None,
) -> None:
    """Agrega un registro de auditoría a la transacción en curso.

    No hace commit: el registro se confirma junto con el cambio que describe, o se
    descarta con él si la operación falla.
    """
    sesion.add(
        RegistroAuditoria(
            usuario_id=usuario_id,
            accion=accion,
            entidad=entidad,
            entidad_id=str(entidad_id),
            datos_anteriores=antes,
            datos_nuevos=despues,
        )
    )
