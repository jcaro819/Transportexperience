"""Esquemas de los domicilios (HU-06, HU-07). Son el contrato con el frontend.

Coordenadas en grados decimales (6 decimales, ~11 cm). Dinero en pesos enteros.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.modulos.domicilios.modelos import Domicilio, EstadoDomicilio
from app.modulos.pagos.esquemas import PagoResumen
from app.modulos.reportes.esquemas import ActaCrear


class CambioDeEstado(BaseModel):
    """Avance de la entrega, sin saltar pasos: asignado → recogido → en_camino → entregado.

    Con `entregado`, `acta` (opcional) anota el estado de la unidad en el acta de entrega.
    """

    estado: Literal["recogido", "en_camino", "entregado"]
    acta: ActaCrear | None = None


class CancelacionPorDespacho(BaseModel):
    motivo: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=5, max_length=500),
        Field(examples=["El cliente no estaba en la dirección y pidió recoger en el local."]),
    ]


class CambioRastreo(BaseModel):
    """Un cambio de estado en el rastreo público: solo el estado y la hora."""

    model_config = ConfigDict(from_attributes=True)

    estado: EstadoDomicilio = Field(validation_alias="estado_nuevo")
    en: datetime = Field(validation_alias="cambiado_en")


class RastreoPublico(BaseModel):
    """Lo que ve cualquiera con el código (SRS 3.6.4). Sin dirección ni datos personales."""

    model_config = ConfigDict(from_attributes=True)

    codigo_rastreo: str
    estado: EstadoDomicilio
    cambios: list[CambioRastreo]


Latitud = Annotated[Decimal, Field(ge=-90, le=90, decimal_places=6, examples=["7.119300"])]
Longitud = Annotated[Decimal, Field(ge=-180, le=180, decimal_places=6, examples=["-73.122700"])]


class ZonaRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    tarifa_envio: int = Field(description="Pesos por entrega en esta zona.")
    poligono: dict[str, Any] = Field(
        description="GeoJSON Polygon, coordenadas `[longitud, latitud]`: se dibuja tal cual."
    )


class Cobertura(BaseModel):
    """La zona que cubre un punto y lo que cuesta el envío allí."""

    zona_id: int
    zona: str
    tarifa_envio: int


class DomicilioCrear(BaseModel):
    """Domicilio para un alquiler o una compra que aún no se ha pagado."""

    alquiler_id: int | None = Field(None, gt=0)
    venta_id: int | None = Field(None, gt=0)
    direccion: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=5, max_length=200),
        Field(examples=["Calle 36 # 19-20, apto 301"]),
    ]
    indicaciones: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, max_length=200),
        Field(examples=["Portería del edificio azul."]),
    ] = None
    latitud: Latitud = Field(description="Del punto que el cliente marcó en el mapa.")
    longitud: Longitud

    @model_validator(mode="after")
    def _una_operacion(self) -> Self:
        if (self.alquiler_id is None) == (self.venta_id is None):
            raise ValueError("Envía `alquiler_id` o `venta_id`, uno de los dos.")
        return self


class AsignacionCrear(BaseModel):
    domiciliario_id: int = Field(gt=0, description="De `/domicilios/domiciliarios-disponibles`.")
    vehiculo_transporte_id: int | None = Field(
        None,
        gt=0,
        description="Unidad de la flota que usa el domiciliario (opcional). Queda "
        "`asignado_a_domicilio` mientras dura la entrega.",
    )


class PersonaContacto(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre_completo: str
    telefono: str | None


class ZonaResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str


class VehiculoTransporte(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: str


class DomicilioRespuesta(BaseModel):
    id: int
    codigo_rastreo: str = Field(description="Para seguir el pedido (HU-07).")
    alquiler_id: int | None
    venta_id: int | None
    estado: EstadoDomicilio
    zona: ZonaResumen
    valor_envio: int = Field(description="Ya sumado al total de la operación.")
    total_operacion: int = Field(description="Total del alquiler o la compra, con el envío.")
    direccion: str
    indicaciones: str | None
    latitud: Decimal
    longitud: Decimal
    cliente: PersonaContacto
    domiciliario: PersonaContacto | None
    vehiculo_transporte: VehiculoTransporte | None = Field(
        description="El vehículo que lleva el domiciliario, si usa uno de la flota."
    )
    motivo_cancelacion: str | None
    creado_en: datetime

    @classmethod
    def desde(cls, domicilio: Domicilio, valor_envio: int, total: int) -> Self:
        return cls(
            id=domicilio.id,
            codigo_rastreo=domicilio.codigo_rastreo,
            alquiler_id=domicilio.alquiler_id,
            venta_id=domicilio.venta_id,
            estado=domicilio.estado,
            zona=ZonaResumen.model_validate(domicilio.zona),
            valor_envio=valor_envio,
            total_operacion=total,
            direccion=domicilio.direccion,
            indicaciones=domicilio.indicaciones,
            latitud=domicilio.latitud,
            longitud=domicilio.longitud,
            cliente=PersonaContacto.model_validate(domicilio.cliente),
            domiciliario=PersonaContacto.model_validate(domicilio.domiciliario)
            if domicilio.domiciliario
            else None,
            vehiculo_transporte=VehiculoTransporte.model_validate(domicilio.vehiculo_transporte)
            if domicilio.vehiculo_transporte
            else None,
            motivo_cancelacion=domicilio.motivo_cancelacion,
            creado_en=domicilio.creado_en,
        )


class CancelacionDomicilioRespuesta(BaseModel):
    domicilio: DomicilioRespuesta
    devolucion: PagoResumen | None = Field(
        description="Devolución del valor del envío, si la operación estaba pagada."
    )
