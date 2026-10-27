"""Esquemas de la gestión del inventario por el administrador (HU-10, SRS 3.1.4).

Crear y editar tipos de vehículo, modelos, unidades y productos. En las ediciones
(``...Actualizar``) solo se aplican los campos enviados; omitir un campo es no cambiarlo.

Lo que **no** se edita aquí, a propósito:

- El **estado** de una unidad: cambia con sus flujos (alquiler, venta, mantenimiento).
- El **stock** de un producto: se mueve con un ajuste (``AjusteStock``), sobre la fila
  bloqueada, para que una edición nunca pise el descuento de una compra simultánea.
- El **código** de una unidad o un producto y el **modelo** de una unidad: son su
  identidad (la etiqueta física, los alquileres y ventas que ya la nombran).
"""

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.modulos.inventario.esquemas import TipoVehiculoRespuesta
from app.modulos.inventario.modelos import CategoriaProducto, EstadoVehiculo

Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
TextoLargo = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
UrlImagen = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=500, pattern=r"^https?://\S+$"),
    Field(examples=["https://transportexperience.test/img/urbano-350.jpg"]),
]
Pesos = Annotated[int, Field(gt=0, le=1_000_000_000, description="Pesos enteros.")]
Codigo = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{2,19}$"
    ),
    Field(
        description="Letras, números y guiones (3 a 20). Se guarda en mayúsculas.",
        examples=["MON-0010"],
    ),
]


def _sin_nulos(modelo: BaseModel, campos: tuple[str, ...]) -> None:
    """Enviar en null un campo obligatorio no tiene sentido: hay que omitirlo."""
    for campo in campos:
        if campo in modelo.model_fields_set and getattr(modelo, campo) is None:
            raise ValueError(f"'{campo}' no puede ser null; omítelo si no quieres cambiarlo.")


# --- Tipos de vehículo ----------------------------------------------------------------------


class TipoVehiculoCrear(BaseModel):
    nombre: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=50)]
    usa_bateria: bool


class TipoVehiculoActualizar(BaseModel):
    nombre: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=50)] | None
    ) = None
    usa_bateria: bool | None = None
    activo: bool | None = Field(None, description="false lo oculta del catálogo con sus modelos.")

    @model_validator(mode="after")
    def _validar(self) -> Self:
        _sin_nulos(self, ("nombre", "usa_bateria", "activo"))
        return self


class TipoVehiculoGestion(TipoVehiculoRespuesta):
    activo: bool


# --- Modelos (fichas del catálogo) ----------------------------------------------------------


class ModeloCrear(BaseModel):
    tipo_vehiculo_id: int = Field(gt=0)
    nombre: Texto
    marca: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = None
    descripcion: TextoLargo | None = None
    imagen_url: UrlImagen | None = None
    tarifa_diaria: Pesos | None = Field(None, description="null: no se alquila.")
    precio_venta: Pesos | None = Field(None, description="null: no se vende.")

    @model_validator(mode="after")
    def _alquila_o_vende(self) -> Self:
        if self.tarifa_diaria is None and self.precio_venta is None:
            raise ValueError("Un modelo debe tener tarifa diaria, precio de venta o ambos.")
        return self


class ModeloActualizar(BaseModel):
    """``tarifa_diaria`` o ``precio_venta`` en null: el modelo deja de alquilarse o venderse.

    Las operaciones ya hechas no cambian: guardan el precio del momento.
    """

    tipo_vehiculo_id: int | None = Field(None, gt=0)
    nombre: Texto | None = None
    marca: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = None
    descripcion: TextoLargo | None = None
    imagen_url: UrlImagen | None = None
    tarifa_diaria: Pesos | None = None
    precio_venta: Pesos | None = None
    activo: bool | None = Field(None, description="false lo saca del catálogo al instante.")

    @model_validator(mode="after")
    def _validar(self) -> Self:
        _sin_nulos(self, ("tipo_vehiculo_id", "nombre", "activo"))
        return self


class ModeloGestion(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: TipoVehiculoRespuesta
    nombre: str
    marca: str | None
    descripcion: str | None
    imagen_url: str | None
    tarifa_diaria: int | None
    precio_venta: int | None
    activo: bool


# --- Unidades -------------------------------------------------------------------------------


class UnidadCrear(BaseModel):
    """Una unidad nueva entra ``disponible``."""

    codigo: Codigo
    modelo_id: int = Field(gt=0)
    nivel_bateria: int | None = Field(
        None, ge=0, le=100, description="Solo si el tipo usa batería."
    )
    ubicacion: Annotated[str, StringConstraints(strip_whitespace=True, max_length=150)] | None = (
        None
    )
    observaciones: TextoLargo | None = None


class UnidadActualizar(BaseModel):
    nivel_bateria: int | None = Field(None, ge=0, le=100)
    ubicacion: Annotated[str, StringConstraints(strip_whitespace=True, max_length=150)] | None = (
        None
    )
    observaciones: TextoLargo | None = None


# --- Productos (accesorios y repuestos) -----------------------------------------------------


class ProductoCrear(BaseModel):
    codigo: Codigo
    nombre: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
    categoria: CategoriaProducto
    descripcion: TextoLargo | None = None
    imagen_url: UrlImagen | None = None
    precio_venta: Pesos
    stock: int = Field(0, ge=0, le=1_000_000, description="Stock inicial.")
    stock_minimo: int = Field(0, ge=0, le=1_000_000, description="En o bajo este número, alerta.")


class ProductoActualizar(BaseModel):
    nombre: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
        | None
    ) = None
    categoria: CategoriaProducto | None = None
    descripcion: TextoLargo | None = None
    imagen_url: UrlImagen | None = None
    precio_venta: Pesos | None = None
    stock_minimo: int | None = Field(None, ge=0, le=1_000_000)
    activo: bool | None = Field(None, description="false lo saca de la venta al instante.")

    @model_validator(mode="after")
    def _validar(self) -> Self:
        _sin_nulos(self, ("nombre", "categoria", "precio_venta", "stock_minimo", "activo"))
        return self


class AjusteStock(BaseModel):
    """Entrada (positiva) o salida (negativa) de stock, con su motivo. Queda en auditoría."""

    cantidad: int = Field(
        ge=-1_000_000, le=1_000_000, description="+5: llegaron 5. -2: se dañaron 2.", examples=[5]
    )
    motivo: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=5, max_length=300),
        Field(examples=["Llegó el pedido del proveedor (factura 1234)."]),
    ]

    @model_validator(mode="after")
    def _distinto_de_cero(self) -> Self:
        if self.cantidad == 0:
            raise ValueError("La cantidad del ajuste no puede ser 0.")
        return self


class ProductoGestion(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: str
    nombre: str
    categoria: CategoriaProducto
    descripcion: str | None
    imagen_url: str | None
    precio_venta: int
    stock: int
    stock_minimo: int
    activo: bool
    bajo_stock: bool = Field(description="true si `stock` está en o bajo `stock_minimo`.")


class ResumenInventario(BaseModel):
    """Estado de la flota y del stock de un vistazo."""

    total_unidades: int
    unidades_por_estado: dict[EstadoVehiculo, int]
    productos_activos: int
    productos_bajo_stock: int
