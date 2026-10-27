"""Esquemas de los alquileres (HU-03). Son el contrato con el frontend.

Todo el dinero va en pesos colombianos enteros. Las fechas del alquiler son inclusivas.
"""

from datetime import date, datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modulos.alquileres.modelos import Alquiler, EstadoAlquiler
from app.modulos.inventario.esquemas import ModeloResumen
from app.modulos.inventario.modelos import EstadoVehiculo
from app.modulos.pagos.modelos import EstadoPago


class AlquilerCrear(BaseModel):
    """Reserva de un modelo del catálogo. El sistema asigna una unidad libre."""

    modelo_id: int = Field(gt=0, description="El `id` del modelo en `/catalogo/modelos`.")
    fecha_inicio: date = Field(description="Primer día del alquiler (AAAA-MM-DD), desde hoy.")
    fecha_fin: date = Field(description="Último día del alquiler, inclusive.")


class PagoAlquilerCrear(BaseModel):
    metodo_pago: Annotated[
        str,
        StringConstraints(strip_whitespace=True, to_lower=True, min_length=1, max_length=20),
        Field(description="Código del método de pago habilitado.", examples=["tarjeta", "pse"]),
    ]


class CancelacionAlquiler(BaseModel):
    motivo: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, max_length=500),
        Field(examples=["Cambié de planes."]),
    ] = None


class ReasignacionAlquiler(BaseModel):
    vehiculo_id: int | None = Field(
        None,
        gt=0,
        description=(
            "Unidad del mismo modelo a la que se mueve el alquiler. Sin este campo, el "
            "sistema escoge la primera libre en esas fechas."
        ),
    )


class VehiculoDelAlquiler(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: str
    modelo: ModeloResumen
    estado: EstadoVehiculo = Field(description="Estado físico actual de la unidad.")


class AlquilerRespuesta(BaseModel):
    id: int
    cliente_id: int
    vehiculo: VehiculoDelAlquiler
    fecha_inicio: date
    fecha_fin: date
    dias: int = Field(description="Días cobrados, contando inicio y fin.")
    tarifa_diaria: int = Field(description="Tarifa del momento de la reserva, en pesos.")
    subtotal: int
    valor_envio: int = Field(description="0 si no hay domicilio.")
    total: int = Field(description="Lo que se cobra: subtotal + envío.")
    estado: EstadoAlquiler
    expira_en: datetime | None = Field(
        description=(
            "Solo en `pendiente_pago`: hasta cuándo se guarda el vehículo sin pagar (15 min)."
        )
    )
    motivo_cancelacion: str | None
    creado_en: datetime

    @classmethod
    def desde(cls, alquiler: Alquiler, estado: EstadoAlquiler) -> Self:
        """``estado`` es el vigente (un pendiente vencido se muestra ``expirado``)."""
        return cls(
            id=alquiler.id,
            cliente_id=alquiler.cliente_id,
            vehiculo=VehiculoDelAlquiler.model_validate(alquiler.vehiculo),
            fecha_inicio=alquiler.fecha_inicio,
            fecha_fin=alquiler.fecha_fin,
            dias=alquiler.dias,
            tarifa_diaria=alquiler.tarifa_diaria,
            subtotal=alquiler.subtotal,
            valor_envio=alquiler.valor_envio,
            total=alquiler.total,
            estado=estado,
            expira_en=alquiler.expira_en,
            motivo_cancelacion=alquiler.motivo_cancelacion,
            creado_en=alquiler.creado_en,
        )


class PagoResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    referencia: str
    estado: EstadoPago
    monto: int
    proveedor: str = Field(description="`falso` en desarrollo; `wompi` desde HU-05.")


class PagoAlquilerRespuesta(BaseModel):
    """El alquiler como quedó y el intento de pago."""

    alquiler: AlquilerRespuesta
    pago: PagoResumen
