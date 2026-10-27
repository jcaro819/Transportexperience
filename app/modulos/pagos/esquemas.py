"""Esquemas de pagos compartidos por las operaciones que cobran (alquileres, ventas)."""

from pydantic import BaseModel, ConfigDict, Field

from app.modulos.pagos.modelos import EstadoPago, TipoPago


class PagoResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    referencia: str
    tipo: TipoPago = Field(description="`cobro`, o `compensacion` si es una devolución.")
    estado: EstadoPago
    monto: int
    proveedor: str = Field(description="`falso` en desarrollo; `wompi` desde HU-05.")
