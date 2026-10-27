"""Esquemas del rastreo GPS (HU-08). Son el contrato con el frontend y con los dispositivos.

Coordenadas en grados decimales con 6 decimales (~11 cm): si llegan más, se redondean.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.modulos.inventario.esquemas import ModeloResumen
from app.modulos.inventario.modelos import EstadoVehiculo
from app.modulos.rastreo.modelos import FuenteGps

Senal = Literal["en_linea", "sin_senal", "sin_datos"]


class PosicionCrear(BaseModel):
    """Lo que envía el dispositivo GPS (o el simulador) cada 5 segundos."""

    latitud: Annotated[Decimal, Field(ge=-90, le=90, examples=["7.119300"])]
    longitud: Annotated[Decimal, Field(ge=-180, le=180, examples=["-73.122700"])]
    precision_metros: Decimal | None = Field(
        None, ge=0, le=9999, description="Precisión que reporta el GPS (HU-08 pide < 10 m)."
    )
    velocidad_kmh: Decimal | None = Field(None, ge=0, le=200)
    nivel_bateria: int | None = Field(None, ge=0, le=100)
    registrado_en: AwareDatetime | None = Field(
        None,
        description="Hora en que el dispositivo tomó la posición, con zona horaria. Si falta, "
        "se usa la hora de llegada.",
    )


class PosicionRecibida(BaseModel):
    vehiculo_codigo: str
    registrado_en: datetime


class ClaveGpsCrear(BaseModel):
    fuente: FuenteGps = Field(
        description="`dispositivo` para un GPS real, `simulador` para el simulador de desarrollo."
    )


class ClaveGpsEmitida(BaseModel):
    """La clave en claro se muestra **una sola vez**: en la base solo queda su hash."""

    vehiculo_id: int
    vehiculo_codigo: str
    fuente: FuenteGps
    clave: str = Field(description="Va en el encabezado `X-Clave-Gps` de cada posición.")
    emitida_en: datetime
    aviso: str = "Guarda esta clave: no se vuelve a mostrar. Emitir otra invalida esta."


class PosicionRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    latitud: Decimal
    longitud: Decimal
    precision_metros: Decimal | None
    velocidad_kmh: Decimal | None
    nivel_bateria: int | None
    registrado_en: datetime
    recibido_en: datetime


class VehiculoEnMapa(BaseModel):
    """Un vehículo de la flota en el mapa, con su última posición y el estado de la señal."""

    vehiculo_id: int
    codigo: str
    modelo: ModeloResumen
    estado: EstadoVehiculo = Field(description="Estado operativo de la unidad.")
    senal: Senal = Field(
        description="`en_linea`: reportó hace poco. `sin_senal`: no reporta hace más del "
        "umbral (30 s, configurable). `sin_datos`: nunca ha reportado."
    )
    segundos_sin_reportar: int | None
    posicion: PosicionRespuesta | None
