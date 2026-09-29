"""Modelos del módulo de inventario (HU-02, HU-09, HU-10) y de novedades (SRS 3.1.8).

Los vehículos son unidades únicas: cada monopatín tiene su código y su estado. Lo que
comparten las unidades iguales (nombre, foto, tarifa, precio) vive en ``ModeloVehiculo``,
que es lo que muestra el catálogo. Los accesorios y repuestos son ``Producto`` con stock.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.comun.modelos import ConMarcasDeTiempo, Dinero, tipo_estado
from app.db import Base


class EstadoVehiculo(StrEnum):
    """Estado operativo actual de una unidad (SRS 3.3.6). Transiciones en el servicio."""

    DISPONIBLE = "disponible"
    RESERVADO = "reservado"
    ALQUILADO = "alquilado"
    VENDIDO = "vendido"
    MANTENIMIENTO = "mantenimiento"
    ASIGNADO_A_DOMICILIO = "asignado_a_domicilio"


class CategoriaProducto(StrEnum):
    ACCESORIO = "accesorio"
    REPUESTO = "repuesto"


class TipoNovedad(StrEnum):
    """Tipos de novedad del SRS 3.1.8, más ``mantenimiento`` para la inactivación de HU-09."""

    DANO = "dano"
    FALLA = "falla"
    PERDIDA_ACCESORIO = "perdida_accesorio"
    BATERIA_BAJA = "bateria_baja"
    INCIDENTE = "incidente"
    MANTENIMIENTO = "mantenimiento"


class EstadoNovedad(StrEnum):
    ABIERTA = "abierta"
    CERRADA = "cerrada"


class TipoVehiculo(ConMarcasDeTiempo, Base):
    """Cicla, patín, monopatín eléctrico... Configurable por el administrador (SRS 3.5.3)."""

    __tablename__ = "tipos_vehiculo"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(50), unique=True)
    usa_bateria: Mapped[bool]
    activo: Mapped[bool] = mapped_column(default=True, server_default=true())


class ModeloVehiculo(ConMarcasDeTiempo, Base):
    """Ficha del catálogo, compartida por todas las unidades iguales.

    Un modelo sin ``tarifa_diaria`` no se alquila; uno sin ``precio_venta`` no se vende.
    """

    __tablename__ = "modelos_vehiculo"
    __table_args__ = (
        CheckConstraint(
            "tarifa_diaria IS NOT NULL OR precio_venta IS NOT NULL", name="alquila_o_vende"
        ),
        CheckConstraint("tarifa_diaria > 0", name="tarifa_diaria_positiva"),
        CheckConstraint("precio_venta > 0", name="precio_venta_positivo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo_vehiculo_id: Mapped[int] = mapped_column(ForeignKey("tipos_vehiculo.id"), index=True)
    marca: Mapped[str | None] = mapped_column(String(60))
    nombre: Mapped[str] = mapped_column(String(100))
    descripcion: Mapped[str | None] = mapped_column(Text)
    imagen_url: Mapped[str | None] = mapped_column(String(500))
    tarifa_diaria: Mapped[int | None] = mapped_column(Dinero)
    precio_venta: Mapped[int | None] = mapped_column(Dinero)
    activo: Mapped[bool] = mapped_column(default=True, server_default=true())

    tipo: Mapped[TipoVehiculo] = relationship()


class Vehiculo(ConMarcasDeTiempo, Base):
    """Unidad física con código único, estado propio y posición GPS."""

    __tablename__ = "vehiculos"
    __table_args__ = (
        CheckConstraint("nivel_bateria BETWEEN 0 AND 100", name="nivel_bateria_rango"),
        # El catálogo filtra por modelo y estado (SRS 3.4.1: < 3 s).
        Index("ix_vehiculos_modelo_estado", "modelo_id", "estado"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    modelo_id: Mapped[int] = mapped_column(ForeignKey("modelos_vehiculo.id"))
    estado: Mapped[EstadoVehiculo] = mapped_column(
        tipo_estado(EstadoVehiculo, "estado_vehiculo"),
        default=EstadoVehiculo.DISPONIBLE,
        server_default=EstadoVehiculo.DISPONIBLE.value,
    )
    nivel_bateria: Mapped[int | None] = mapped_column(SmallInteger)
    ubicacion: Mapped[str | None] = mapped_column(String(150))
    observaciones: Mapped[str | None] = mapped_column(Text)

    modelo: Mapped[ModeloVehiculo] = relationship()


class Producto(ConMarcasDeTiempo, Base):
    """Accesorio o repuesto que se vende por cantidad (cascos, cargadores...)."""

    __tablename__ = "productos"
    __table_args__ = (
        # La base misma impide vender más de lo que hay, aun con compras simultáneas.
        CheckConstraint("stock >= 0", name="stock_no_negativo"),
        CheckConstraint("stock_minimo >= 0", name="stock_minimo_no_negativo"),
        CheckConstraint("precio_venta > 0", name="precio_venta_positivo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    categoria: Mapped[CategoriaProducto] = mapped_column(
        tipo_estado(CategoriaProducto, "categoria_producto")
    )
    descripcion: Mapped[str | None] = mapped_column(Text)
    imagen_url: Mapped[str | None] = mapped_column(String(500))
    precio_venta: Mapped[int] = mapped_column(Dinero)
    stock: Mapped[int] = mapped_column(default=0, server_default="0")
    # HU-10: alerta de bajo stock cuando stock <= stock_minimo.
    stock_minimo: Mapped[int] = mapped_column(default=0, server_default="0")
    activo: Mapped[bool] = mapped_column(default=True, server_default=true())


class NovedadVehiculo(Base):
    """Daño, falla, batería baja, mantenimiento... reportado sobre una unidad.

    Una novedad crítica pasa el vehículo a mantenimiento; solo un operador la cierra y
    devuelve la unidad a servicio. Una novedad abierta impide volver a ``disponible``.
    """

    __tablename__ = "novedades_vehiculo"
    __table_args__ = (
        Index("ix_novedades_vehiculo_vehiculo_estado", "vehiculo_id", "estado"),
        CheckConstraint(
            "(estado = 'cerrada') = (cerrada_en IS NOT NULL AND cerrada_por_id IS NOT NULL)",
            name="cierre_completo",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    vehiculo_id: Mapped[int] = mapped_column(ForeignKey("vehiculos.id"))
    tipo: Mapped[TipoNovedad] = mapped_column(tipo_estado(TipoNovedad, "tipo_novedad"))
    descripcion: Mapped[str] = mapped_column(Text)
    es_critica: Mapped[bool]
    estado: Mapped[EstadoNovedad] = mapped_column(
        tipo_estado(EstadoNovedad, "estado_novedad"),
        default=EstadoNovedad.ABIERTA,
        server_default=EstadoNovedad.ABIERTA.value,
    )
    reportada_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cerrada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    cerrada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    solucion: Mapped[str | None] = mapped_column(Text)
