"""Esquemas de pagos (HU-05). Son el contrato con el frontend.

Todo el dinero va en pesos colombianos enteros.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modulos.pagos.modelos import EstadoPago, TipoPago

_Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class TarjetaCrear(BaseModel):
    token: _Texto = Field(
        description=(
            "Token de la tarjeta, generado por el frontend con la llave pública "
            "(`POST /tokens/cards` de Wompi). El número de la tarjeta nunca llega a este backend."
        ),
        examples=["tok_test_12345_abcdef"],
    )
    cuotas: int = Field(1, ge=1, le=36)


class PseCrear(BaseModel):
    tipo_persona: Literal["natural", "juridica"] = "natural"
    tipo_documento: Literal["CC", "NIT"] = "CC"
    documento: Annotated[
        str,
        StringConstraints(strip_whitespace=True, pattern=r"^\d{5,15}$"),
        Field(description="Solo dígitos.", examples=["1098765432"]),
    ]
    banco: _Texto = Field(description="`codigo` de `/pagos/pse/bancos`.", examples=["1"])


class PagoCrear(BaseModel):
    """Cómo paga el cliente. Con la pasarela falsa basta `metodo_pago`."""

    metodo_pago: Annotated[
        str,
        StringConstraints(strip_whitespace=True, to_lower=True, min_length=1, max_length=20),
        Field(description="Código del método de pago habilitado.", examples=["tarjeta", "pse"]),
    ]
    acepta_terminos: bool = Field(
        False,
        description=(
            "Con Wompi es obligatorio: el cliente aceptó los términos y la autorización de "
            "datos (enlaces en `/pagos/configuracion`)."
        ),
    )
    tarjeta: TarjetaCrear | None = None
    pse: PseCrear | None = None


class PagoResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    referencia: str
    tipo: TipoPago = Field(description="`cobro`, o `compensacion` si es una devolución.")
    estado: EstadoPago
    monto: int
    proveedor: str = Field(description="`falso` en desarrollo; `wompi` con el sandbox.")
    url_redireccion: str | None = Field(
        None, description="PSE: envía al cliente a esta página del banco para que pague."
    )


class PagoDetalle(PagoResumen):
    alquiler_id: int | None
    venta_id: int | None
    detalle_error: str | None = Field(description="Por qué falló, o el motivo de la devolución.")
    aprobado_en: datetime | None
    creado_en: datetime


class ConfiguracionPagos(BaseModel):
    """Lo que el frontend necesita antes de cobrar."""

    proveedor: str
    metodos: list[str] = Field(description="Códigos de los métodos de pago habilitados.")
    llave_publica: str | None = Field(description="Para tokenizar la tarjeta. null en `falso`.")
    url_api: str | None = Field(description="API de Wompi sandbox para tokenizar.")
    terminos_url: str | None = Field(description="Términos de la pasarela: muéstralos.")
    datos_personales_url: str | None = Field(description="Autorización de datos personales.")


class BancoPse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo: str
    nombre: str


class DevolucionEjecutada(BaseModel):
    nota: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=5, max_length=500),
        Field(examples=["Reembolso hecho en el panel de Wompi el 27/10/2026."]),
    ]


class EventoRecibido(BaseModel):
    recibido: bool = True
