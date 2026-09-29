"""Esquemas del portal institucional (HU-01). Son el contrato con el frontend."""

from datetime import datetime, time
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.modulos.portal.modelos import DiaSemana, SeccionPortal


class SeccionRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seccion: SeccionPortal
    titulo: str
    contenido: str
    actualizado_en: datetime


class HorarioDia(BaseModel):
    """Horario de un día. Si ``abierto`` es false, las horas vienen en null."""

    dia: DiaSemana
    abierto: bool
    hora_apertura: time | None = Field(examples=["07:00:00"])
    hora_cierre: time | None = Field(examples=["19:00:00"])


class PortalRespuesta(BaseModel):
    """Todo lo que muestra el portal, en una sola petición (HU-01: carga < 2 s)."""

    secciones: list[SeccionRespuesta] = Field(
        description="Misión, visión y contacto, en ese orden. Solo las que tienen texto."
    )
    horarios: list[HorarioDia] = Field(description="Siempre los 7 días, de lunes a domingo.")


class SeccionEditar(BaseModel):
    titulo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
    contenido: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=2, max_length=10_000)
    ]


class HorarioEditar(BaseModel):
    hora_apertura: time = Field(examples=["07:00"])
    hora_cierre: time = Field(examples=["19:00"])

    @model_validator(mode="after")
    def _cierre_despues_de_apertura(self) -> Self:
        if self.hora_cierre <= self.hora_apertura:
            raise ValueError("La hora de cierre debe ser posterior a la de apertura.")
        return self
