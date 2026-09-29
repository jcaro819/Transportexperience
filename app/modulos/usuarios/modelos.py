"""Modelos del módulo de usuarios (HU-12)."""

from enum import StrEnum

from sqlalchemy import CheckConstraint, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.comun.modelos import ConMarcasDeTiempo, tipo_estado
from app.db import Base


class Rol(StrEnum):
    """Los cuatro roles del SRS. HU-12 nombra tres; el domiciliario lo exigen HU-06 y HU-07."""

    CLIENTE = "cliente"
    ADMINISTRADOR = "administrador"
    OPERADOR = "operador"
    DOMICILIARIO = "domiciliario"


class Usuario(ConMarcasDeTiempo, Base):
    """Persona que usa el sistema. Un usuario tiene un solo rol."""

    __tablename__ = "usuarios"
    __table_args__ = (CheckConstraint("correo = lower(correo)", name="correo_minusculas"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre_completo: Mapped[str] = mapped_column(String(150))
    correo: Mapped[str] = mapped_column(String(254), unique=True)
    telefono: Mapped[str | None] = mapped_column(String(20))
    hash_contrasena: Mapped[str] = mapped_column(String(255))
    rol: Mapped[Rol] = mapped_column(tipo_estado(Rol, "rol"), index=True)
    activo: Mapped[bool] = mapped_column(default=True, server_default=true())
