"""Reglas de negocio del catálogo público (HU-02).

Qué significa "disponible" (CLAUDE.md 7.2):

- **Hoy**: la unidad está físicamente ``disponible`` y ningún alquiler activo la ocupa hoy
  (uno confirmado que empieza hoy ya la compromete, aunque no se haya entregado).
- **En un rango futuro**: ningún alquiler activo se cruza con el rango, y la unidad está
  ``disponible``, ``alquilada`` o con un domiciliario: esos estados son temporales y sus
  fechas ya están en ``alquileres``. Una unidad en ``mantenimiento`` no cuenta, porque no
  se sabe cuándo vuelve; ``vendida`` y ``reservada`` (compra en curso) tampoco.

Los modelos o tipos inactivos no aparecen en el catálogo.
"""

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload

from app.comun import fechas
from app.comun.paginacion import ParametrosPagina, ResultadoPagina, paginar
from app.modulos.alquileres.servicio import consulta_vehiculos_ocupados
from app.modulos.inventario.esquemas import FiltrosCatalogo, Modalidad
from app.modulos.inventario.excepciones import (
    FechasInvalidas,
    ModeloNoEncontrado,
    ModeloNoSeAlquila,
    RangoDeTarifaInvalido,
)
from app.modulos.inventario.modelos import EstadoVehiculo, ModeloVehiculo, TipoVehiculo, Vehiculo

# Estados temporales: la unidad vuelve a estar libre cuando termina lo que la ocupa.
_RESERVABLES_A_FUTURO = (
    EstadoVehiculo.DISPONIBLE,
    EstadoVehiculo.ALQUILADO,
    EstadoVehiculo.ASIGNADO_A_DOMICILIO,
)


@dataclass(frozen=True)
class ModeloConDisponibilidad:
    modelo: ModeloVehiculo
    disponibles_hoy: int


@dataclass(frozen=True)
class ModeloConUnidades:
    modelo: ModeloVehiculo
    unidades: list[Vehiculo]


@dataclass(frozen=True)
class ResultadoDisponibilidad:
    modelo_id: int
    fecha_inicio: date
    fecha_fin: date
    dias: int
    unidades_libres: int

    @property
    def disponible(self) -> bool:
        return self.unidades_libres > 0


def _unidades_libres(inicio: date, fin: date, hoy: date, momento: datetime) -> Select:
    """Consulta (id, modelo_id) de las unidades libres durante todo [inicio, fin]."""
    estados = (EstadoVehiculo.DISPONIBLE,) if inicio <= hoy else _RESERVABLES_A_FUTURO
    return select(Vehiculo.id, Vehiculo.modelo_id).where(
        Vehiculo.estado.in_(estados),
        Vehiculo.id.not_in(consulta_vehiculos_ocupados(inicio, fin, momento)),
    )


def _modelos_visibles() -> Select:
    """Modelos activos de tipos activos, con su tipo cargado."""
    return (
        select(ModeloVehiculo)
        .join(ModeloVehiculo.tipo)
        .where(ModeloVehiculo.activo, TipoVehiculo.activo)
        .options(joinedload(ModeloVehiculo.tipo))
    )


def listar_tipos(sesion: Session, parametros: ParametrosPagina) -> ResultadoPagina:
    """Tipos de vehículo activos, para el filtro del catálogo."""
    consulta = select(TipoVehiculo).where(TipoVehiculo.activo).order_by(TipoVehiculo.nombre)
    return paginar(sesion, consulta, parametros)


def listar_modelos(
    sesion: Session,
    parametros: ParametrosPagina,
    filtros: FiltrosCatalogo,
    *,
    hoy: date | None = None,
    momento: datetime | None = None,
) -> ResultadoPagina:
    """Catálogo paginado. Cada elemento es un ``ModeloConDisponibilidad``."""
    if (
        filtros.tarifa_min is not None
        and filtros.tarifa_max is not None
        and filtros.tarifa_min > filtros.tarifa_max
    ):
        raise RangoDeTarifaInvalido()
    hoy = hoy or fechas.hoy()
    momento = momento or fechas.ahora()

    libres = _unidades_libres(hoy, hoy, hoy, momento).subquery()
    conteo = (
        select(libres.c.modelo_id, func.count().label("cantidad"))
        .group_by(libres.c.modelo_id)
        .subquery()
    )
    disponibles = func.coalesce(conteo.c.cantidad, 0)

    consulta = (
        _modelos_visibles()
        .add_columns(disponibles)
        .outerjoin(conteo, conteo.c.modelo_id == ModeloVehiculo.id)
        .order_by(TipoVehiculo.nombre, ModeloVehiculo.nombre, ModeloVehiculo.id)
    )
    if filtros.tipo_id is not None:
        consulta = consulta.where(ModeloVehiculo.tipo_vehiculo_id == filtros.tipo_id)
    if filtros.tarifa_min is not None:
        consulta = consulta.where(ModeloVehiculo.tarifa_diaria >= filtros.tarifa_min)
    if filtros.tarifa_max is not None:
        consulta = consulta.where(ModeloVehiculo.tarifa_diaria <= filtros.tarifa_max)
    if filtros.modalidad == Modalidad.ALQUILER:
        consulta = consulta.where(ModeloVehiculo.tarifa_diaria.is_not(None))
    elif filtros.modalidad == Modalidad.VENTA:
        consulta = consulta.where(ModeloVehiculo.precio_venta.is_not(None))
    if filtros.solo_disponibles:
        consulta = consulta.where(disponibles > 0)

    pagina = paginar(sesion, consulta, parametros, filas=True)
    elementos = [ModeloConDisponibilidad(modelo, cantidad) for modelo, cantidad in pagina.elementos]
    return ResultadoPagina(elementos, pagina.total, pagina.pagina, pagina.tamano)


def _modelo_visible(sesion: Session, modelo_id: int) -> ModeloVehiculo:
    modelo = sesion.scalars(_modelos_visibles().where(ModeloVehiculo.id == modelo_id)).first()
    if modelo is None:
        raise ModeloNoEncontrado()
    return modelo


def obtener_modelo(
    sesion: Session,
    modelo_id: int,
    *,
    hoy: date | None = None,
    momento: datetime | None = None,
) -> ModeloConUnidades:
    """Ficha de un modelo con sus unidades libres hoy (código, ubicación, batería)."""
    hoy = hoy or fechas.hoy()
    momento = momento or fechas.ahora()
    modelo = _modelo_visible(sesion, modelo_id)
    libres = _unidades_libres(hoy, hoy, hoy, momento).with_only_columns(Vehiculo.id)
    unidades = sesion.scalars(
        select(Vehiculo)
        .where(Vehiculo.modelo_id == modelo.id, Vehiculo.id.in_(libres))
        .order_by(Vehiculo.codigo)
    ).all()
    return ModeloConUnidades(modelo, list(unidades))


def consultar_disponibilidad(
    sesion: Session,
    modelo_id: int,
    fecha_inicio: date,
    fecha_fin: date,
    *,
    hoy: date | None = None,
    momento: datetime | None = None,
) -> ResultadoDisponibilidad:
    """Cuántas unidades del modelo están libres durante todo el rango (fechas inclusivas)."""
    hoy = hoy or fechas.hoy()
    momento = momento or fechas.ahora()
    if fecha_inicio < hoy:
        raise FechasInvalidas("La fecha de inicio ya pasó.")
    if fecha_fin < fecha_inicio:
        raise FechasInvalidas("La fecha de fin es anterior a la de inicio.")
    modelo = _modelo_visible(sesion, modelo_id)
    if modelo.tarifa_diaria is None:
        raise ModeloNoSeAlquila()

    libres = _unidades_libres(fecha_inicio, fecha_fin, hoy, momento).subquery()
    cantidad = sesion.scalar(
        select(func.count()).select_from(libres).where(libres.c.modelo_id == modelo.id)
    )
    return ResultadoDisponibilidad(
        modelo_id=modelo.id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        dias=(fecha_fin - fecha_inicio).days + 1,
        unidades_libres=cantidad or 0,
    )
