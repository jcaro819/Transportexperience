"""Esquemas de las ventas (HU-04). Son el contrato con el frontend.

Todo el dinero va en pesos colombianos enteros.
"""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.modulos.pagos.esquemas import PagoResumen
from app.modulos.pagos.modelos import EstadoPago, Pago
from app.modulos.ventas.modelos import EstadoVenta, ItemVenta, Venta

# Topes de cordura para una sola compra, no reglas de negocio.
_MAX_VEHICULOS_POR_LINEA = 10
_MAX_PRODUCTOS_POR_LINEA = 100


class ItemVehiculoCrear(BaseModel):
    modelo_id: int = Field(gt=0, description="El `id` del modelo en `/catalogo/modelos`.")
    cantidad: int = Field(1, ge=1, le=_MAX_VEHICULOS_POR_LINEA)


class ItemProductoCrear(BaseModel):
    producto_id: int = Field(gt=0, description="El `id` en `/catalogo/productos`.")
    cantidad: int = Field(1, ge=1, le=_MAX_PRODUCTOS_POR_LINEA)


class VentaCrear(BaseModel):
    """El carrito confirmado: vehículos (por modelo) y accesorios o repuestos."""

    vehiculos: list[ItemVehiculoCrear] = Field(default_factory=list)
    productos: list[ItemProductoCrear] = Field(default_factory=list)

    @model_validator(mode="after")
    def _carrito_valido(self) -> Self:
        if not self.vehiculos and not self.productos:
            raise ValueError("La compra debe tener al menos un vehículo o un producto.")
        modelos = [i.modelo_id for i in self.vehiculos]
        productos = [i.producto_id for i in self.productos]
        if len(set(modelos)) != len(modelos) or len(set(productos)) != len(productos):
            raise ValueError("Cada vehículo o producto va una sola vez; usa `cantidad`.")
        return self


class CancelacionVenta(BaseModel):
    motivo: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, max_length=500),
        Field(examples=["Me equivoqué de talla."]),
    ] = None


class ItemVentaRespuesta(BaseModel):
    tipo: Literal["vehiculo", "producto"]
    descripcion: str = Field(description="Nombre del modelo o del producto.")
    codigo: str = Field(description="Código de la unidad o del producto.")
    vehiculo_id: int | None
    producto_id: int | None
    cantidad: int
    precio_unitario: int = Field(description="Precio del momento de la compra, en pesos.")
    subtotal: int

    @classmethod
    def desde(cls, item: ItemVenta) -> Self:
        if item.vehiculo is not None:
            tipo, descripcion, codigo = (
                "vehiculo",
                item.vehiculo.modelo.nombre,
                item.vehiculo.codigo,
            )
        else:
            tipo, descripcion, codigo = "producto", item.producto.nombre, item.producto.codigo
        return cls(
            tipo=tipo,
            descripcion=descripcion,
            codigo=codigo,
            vehiculo_id=item.vehiculo_id,
            producto_id=item.producto_id,
            cantidad=item.cantidad,
            precio_unitario=item.precio_unitario,
            subtotal=item.subtotal,
        )


class VentaRespuesta(BaseModel):
    id: int
    cliente_id: int
    items: list[ItemVentaRespuesta]
    subtotal: int
    valor_envio: int = Field(description="0 si no hay domicilio.")
    total: int = Field(description="Lo que se cobra: subtotal + envío.")
    estado: EstadoVenta
    expira_en: datetime | None = Field(
        description="Solo en `pendiente_pago`: hasta cuándo se guarda la compra sin pagar."
    )
    motivo_cancelacion: str | None
    creado_en: datetime

    @classmethod
    def desde(cls, venta: Venta, estado: EstadoVenta) -> Self:
        """``estado`` es el vigente (una pendiente vencida se muestra ``expirada``)."""
        return cls(
            id=venta.id,
            cliente_id=venta.cliente_id,
            items=[ItemVentaRespuesta.desde(i) for i in venta.items],
            subtotal=venta.subtotal,
            valor_envio=venta.valor_envio,
            total=venta.total,
            estado=estado,
            expira_en=venta.expira_en,
            motivo_cancelacion=venta.motivo_cancelacion,
            creado_en=venta.creado_en,
        )


class PagoVentaRespuesta(BaseModel):
    """La compra como quedó, el intento de pago y, si hubo que devolver, la devolución."""

    venta: VentaRespuesta
    pago: PagoResumen
    devolucion: PagoResumen | None = Field(
        None,
        description=(
            "Solo si el pago se aprobó pero la compra no pudo completarse (una unidad entró "
            "en mantenimiento, o la compra ya había expirado): se registra la devolución."
        ),
    )


class ClienteComprobante(BaseModel):
    nombre_completo: str
    correo: str


class PagoComprobante(BaseModel):
    referencia: str
    metodo: str
    estado: EstadoPago
    aprobado_en: datetime | None


class ComprobantePreliminar(BaseModel):
    """Comprobante preliminar de la compra (HU-04). No es una factura.

    El comprobante definitivo en PDF llega con HU-05.
    """

    numero: str = Field(examples=["PRE-000042"])
    es_preliminar: Literal[True] = True
    leyenda: str
    emitido_en: datetime
    venta_id: int
    fecha_compra: datetime
    cliente: ClienteComprobante
    items: list[ItemVentaRespuesta]
    subtotal: int
    valor_envio: int
    total: int
    estado: EstadoVenta
    pago: PagoComprobante | None = Field(description="El último cobro intentado, si hay.")

    @classmethod
    def desde(
        cls,
        venta: Venta,
        estado: EstadoVenta,
        pago: Pago | None,
        metodo: str | None,
        emitido_en: datetime,
    ) -> Self:
        return cls(
            numero=f"PRE-{venta.id:06d}",
            leyenda="Comprobante preliminar. No es una factura ni prueba de pago.",
            emitido_en=emitido_en,
            venta_id=venta.id,
            fecha_compra=venta.creado_en,
            cliente=ClienteComprobante(
                nombre_completo=venta.cliente.nombre_completo, correo=venta.cliente.correo
            ),
            items=[ItemVentaRespuesta.desde(i) for i in venta.items],
            subtotal=venta.subtotal,
            valor_envio=venta.valor_envio,
            total=venta.total,
            estado=estado,
            pago=None
            if pago is None
            else PagoComprobante(
                referencia=pago.referencia,
                metodo=metodo or "",
                estado=pago.estado,
                aprobado_en=pago.aprobado_en,
            ),
        )
