"""Esquemas de las actas de entrega y recepción (HU-11). Son el contrato con el frontend."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.modulos.reportes.modelos import TipoActa
from app.modulos.reportes.registro import SIN_OBSERVACIONES, DatosActa


class ActaCrear(BaseModel):
    """Lo que anota quien entrega o recibe la unidad. Todo es opcional."""

    estado_vehiculo: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=3, max_length=1000),
        Field(examples=["Sin rayones. Frenos y luces funcionando. Incluye casco."]),
    ] = SIN_OBSERVACIONES
    nivel_bateria: int | None = Field(
        None, ge=0, le=100, description="Porcentaje medido al entregar o recibir (si usa batería)."
    )

    def datos(self) -> DatosActa:
        return DatosActa(self.estado_vehiculo, self.nivel_bateria)


class Conformidad(BaseModel):
    """Firma de conformidad: quién, cuándo y la huella (SHA-256) del PDF que aceptó."""

    conforme_por_id: int
    conforme_por: str
    conforme_en: datetime
    hash_pdf: str = Field(
        description="SHA-256 del PDF del acta. Para verificar un PDF, calcula su SHA-256 y "
        "compáralo: si no coincide, el documento no es el que se aceptó."
    )


class ActaRespuesta(BaseModel):
    id: int
    numero: str = Field(examples=["ACT-000042"])
    tipo: TipoActa
    creado_en: datetime
    vehiculo_id: int
    vehiculo_codigo: str
    modelo: str
    alquiler_id: int | None
    venta_id: int | None
    domicilio_id: int | None
    cliente_id: int
    cliente: str
    estado_vehiculo: str
    nivel_bateria: int | None
    registrada_por: str
    conformidad: Conformidad | None


class VerificacionActa(BaseModel):
    con_conformidad: bool
    coincide: bool | None = Field(
        description="true: el PDF de hoy es el que se aceptó. null: aún no hay conformidad."
    )
    hash_pdf: str | None
