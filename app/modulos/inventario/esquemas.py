"""Esquemas del catálogo público (HU-02). Son el contrato con el frontend.

Todo el dinero va en pesos colombianos enteros.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Annotated, Self

from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from app.modulos.inventario.modelos import ModeloVehiculo, Vehiculo


class Modalidad(StrEnum):
    ALQUILER = "alquiler"
    VENTA = "venta"


@dataclass(frozen=True)
class FiltrosCatalogo:
    """Filtros del catálogo. Todos son opcionales y se combinan entre sí."""

    tipo_id: int | None = None
    tarifa_min: int | None = None
    tarifa_max: int | None = None
    modalidad: Modalidad | None = None
    solo_disponibles: bool = False


def _filtros_catalogo(
    tipo_id: Annotated[
        int | None, Query(gt=0, description="Solo modelos de este tipo de vehículo.")
    ] = None,
    tarifa_min: Annotated[
        int | None, Query(ge=0, description="Tarifa diaria mínima, en pesos.")
    ] = None,
    tarifa_max: Annotated[
        int | None, Query(ge=0, description="Tarifa diaria máxima, en pesos.")
    ] = None,
    modalidad: Annotated[
        Modalidad | None,
        Query(description="`alquiler`: solo los que se alquilan. `venta`: los que se venden."),
    ] = None,
    solo_disponibles: Annotated[
        bool, Query(description="Solo modelos con unidades libres hoy.")
    ] = False,
) -> FiltrosCatalogo:
    return FiltrosCatalogo(tipo_id, tarifa_min, tarifa_max, modalidad, solo_disponibles)


# Úsalo como parámetro de una ruta: ``filtros: FiltrosDelCatalogo``.
FiltrosDelCatalogo = Annotated[FiltrosCatalogo, Depends(_filtros_catalogo)]


class TipoVehiculoRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    usa_bateria: bool


class ModeloCatalogo(BaseModel):
    """Una ficha del catálogo: un modelo y cuántas unidades suyas están libres hoy."""

    id: int
    nombre: str
    marca: str | None
    descripcion: str | None
    imagen_url: str | None
    tipo: TipoVehiculoRespuesta
    tarifa_diaria: int | None = Field(description="Pesos por día. null: no se alquila.")
    precio_venta: int | None = Field(description="Pesos. null: no se vende.")
    se_alquila: bool
    se_vende: bool
    disponibles_hoy: int = Field(description="Unidades que se pueden entregar hoy.")

    @classmethod
    def desde(cls, modelo: ModeloVehiculo, disponibles_hoy: int, **extra) -> Self:
        return cls(
            id=modelo.id,
            nombre=modelo.nombre,
            marca=modelo.marca,
            descripcion=modelo.descripcion,
            imagen_url=modelo.imagen_url,
            tipo=TipoVehiculoRespuesta.model_validate(modelo.tipo),
            tarifa_diaria=modelo.tarifa_diaria,
            precio_venta=modelo.precio_venta,
            se_alquila=modelo.tarifa_diaria is not None,
            se_vende=modelo.precio_venta is not None,
            disponibles_hoy=disponibles_hoy,
            **extra,
        )


class UnidadDisponible(BaseModel):
    """Unidad libre hoy, con su ubicación y batería (SRS 3.1)."""

    model_config = ConfigDict(from_attributes=True)

    codigo: str
    ubicacion: str | None
    nivel_bateria: int | None = Field(description="Porcentaje 0-100. null si no usa batería.")


class ModeloDetalle(ModeloCatalogo):
    """Vista detallada de un modelo: su ficha más las unidades libres hoy."""

    unidades_disponibles: list[UnidadDisponible]

    @classmethod
    def desde_unidades(cls, modelo: ModeloVehiculo, unidades: list[Vehiculo]) -> Self:
        return cls.desde(
            modelo,
            len(unidades),
            unidades_disponibles=[UnidadDisponible.model_validate(u) for u in unidades],
        )


class DisponibilidadRango(BaseModel):
    """Cuántas unidades de un modelo están libres durante todo un rango de fechas."""

    model_config = ConfigDict(from_attributes=True)

    modelo_id: int
    fecha_inicio: date
    fecha_fin: date
    dias: int = Field(description="Días del rango, contando inicio y fin.")
    unidades_libres: int
    disponible: bool = Field(description="true si hay al menos una unidad libre.")
