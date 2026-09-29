"""Paginación de listas (SRS 3.4.6). Ninguna ruta devuelve una tabla completa."""

import math
from dataclasses import dataclass
from typing import Annotated, Any, Generic, TypeVar

from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")

TAMANO_MAXIMO = 100


@dataclass(frozen=True)
class ParametrosPagina:
    pagina: int = 1
    tamano: int = 20

    @property
    def desplazamiento(self) -> int:
        return (self.pagina - 1) * self.tamano


def _parametros_pagina(
    pagina: Annotated[int, Query(ge=1, description="Número de página, desde 1.")] = 1,
    tamano: Annotated[
        int, Query(ge=1, le=TAMANO_MAXIMO, description="Elementos por página (máx. 100).")
    ] = 20,
) -> ParametrosPagina:
    return ParametrosPagina(pagina=pagina, tamano=tamano)


# Úsalo como parámetro de una ruta: ``parametros: Paginacion``.
Paginacion = Annotated[ParametrosPagina, Depends(_parametros_pagina)]


@dataclass(frozen=True)
class ResultadoPagina:
    """Lo que devuelve el servicio: una página de registros y el total sin paginar."""

    elementos: list[Any]
    total: int
    pagina: int
    tamano: int

    @property
    def paginas(self) -> int:
        return math.ceil(self.total / self.tamano) if self.total else 0


class Pagina(BaseModel, Generic[T]):
    """Respuesta paginada. ``paginas`` es el total de páginas disponibles."""

    model_config = ConfigDict(from_attributes=True)

    elementos: list[T]
    total: int
    pagina: int
    tamano: int
    paginas: int


def paginar(
    sesion: Session, consulta: Select, parametros: ParametrosPagina, *, filas: bool = False
) -> ResultadoPagina:
    """Ejecuta ``consulta`` devolviendo solo la página pedida, más el total de filas.

    Con ``filas=True`` cada elemento es una fila con todas las columnas seleccionadas;
    si no, solo la primera (normalmente, el objeto del modelo).
    """
    total = sesion.scalar(select(func.count()).select_from(consulta.order_by(None).subquery()))
    pagina = consulta.limit(parametros.tamano).offset(parametros.desplazamiento)
    elementos = sesion.execute(pagina).all() if filas else sesion.scalars(pagina).all()
    return ResultadoPagina(list(elementos), total or 0, parametros.pagina, parametros.tamano)
