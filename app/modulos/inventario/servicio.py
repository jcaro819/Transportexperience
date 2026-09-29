"""Reglas de negocio del inventario: catálogo público (HU-02) y gestión de la flota (HU-09).

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

from app.auditoria import registrar_auditoria
from app.comun import fechas
from app.comun.errores import PermisoDenegado
from app.comun.paginacion import ParametrosPagina, ResultadoPagina, paginar
from app.modulos.alquileres.modelos import Alquiler
from app.modulos.alquileres.servicio import (
    consulta_alquiler_en_curso,
    consulta_alquileres_vigentes,
    consulta_vehiculos_ocupados,
)
from app.modulos.domicilios.servicio import consulta_domicilios_sin_finalizar
from app.modulos.inventario.esquemas import CierreNovedad, FiltrosCatalogo, Modalidad, NovedadCrear
from app.modulos.inventario.estados import es_transicion_valida, validar_transicion
from app.modulos.inventario.excepciones import (
    FechasInvalidas,
    ModeloNoEncontrado,
    ModeloNoSeAlquila,
    NoPuedeVolverAServicio,
    NovedadNoEncontrada,
    NovedadYaCerrada,
    RangoDeTarifaInvalido,
    TransicionInvalida,
    VehiculoNoEncontrado,
    VehiculoVendido,
)
from app.modulos.inventario.modelos import (
    EstadoNovedad,
    EstadoVehiculo,
    ModeloVehiculo,
    NovedadVehiculo,
    TipoNovedad,
    TipoVehiculo,
    Vehiculo,
)
from app.modulos.usuarios.modelos import Rol, Usuario

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


# --- Gestión de la flota (HU-09, SRS 3.1.8) -----------------------------------------------
#
# Cada operación empieza bloqueando la fila del vehículo (CLAUDE.md 7.1, regla 1), valida
# todo antes de modificar nada, y confirma su transacción al final. Si algo falla, la
# unidad queda exactamente como estaba (SRS 3.3.4).

# Inactivar, cerrar novedades y devolver a servicio: solo el taller.
ROLES_DE_TALLER = frozenset({Rol.ADMINISTRADOR, Rol.OPERADOR})
# Reportar novedades (incluidas críticas): también el domiciliario, que ve la unidad en ruta.
ROLES_QUE_REPORTAN = ROLES_DE_TALLER | {Rol.DOMICILIARIO}


@dataclass(frozen=True)
class ResultadoOperacion:
    vehiculo: Vehiculo
    novedad: NovedadVehiculo
    alquileres_afectados: list[Alquiler]


def _exigir_rol(usuario: Usuario, permitidos: frozenset[Rol]) -> None:
    # Las rutas ya lo exigen; el servicio lo repite para que ninguna llamada futura lo salte.
    if usuario.rol not in permitidos:
        raise PermisoDenegado()


def bloquear_vehiculo(sesion: Session, vehiculo_id: int) -> Vehiculo:
    """``SELECT ... FOR UPDATE`` sobre la unidad: nadie más la toca hasta el commit."""
    vehiculo = sesion.scalars(
        select(Vehiculo)
        .where(Vehiculo.id == vehiculo_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if vehiculo is None:
        raise VehiculoNoEncontrado()
    return vehiculo


def cambiar_estado_vehiculo(
    sesion: Session,
    vehiculo: Vehiculo,
    nuevo: EstadoVehiculo,
    usuario: Usuario | None,
    motivo: str,
) -> None:
    """Único camino para cambiar el estado de una unidad: valida la transición y la audita.

    No hace commit: el cambio y su auditoría se confirman con la operación que lo causa.
    La fila debe estar bloqueada con ``bloquear_vehiculo``.
    """
    anterior = vehiculo.estado
    validar_transicion(anterior, nuevo)
    vehiculo.estado = nuevo
    registrar_auditoria(
        sesion,
        usuario_id=usuario.id if usuario else None,
        accion="cambiar_estado",
        entidad="vehiculos",
        entidad_id=vehiculo.id,
        antes={"estado": anterior.value},
        despues={"estado": nuevo.value, "motivo": motivo},
    )


def listar_vehiculos(
    sesion: Session,
    parametros: ParametrosPagina,
    estado: EstadoVehiculo | None = None,
    modelo_id: int | None = None,
    codigo: str | None = None,
) -> ResultadoPagina:
    """Toda la flota con su estado real, para el personal."""
    consulta = select(Vehiculo).options(joinedload(Vehiculo.modelo)).order_by(Vehiculo.codigo)
    if estado is not None:
        consulta = consulta.where(Vehiculo.estado == estado)
    if modelo_id is not None:
        consulta = consulta.where(Vehiculo.modelo_id == modelo_id)
    if codigo:
        consulta = consulta.where(Vehiculo.codigo.ilike(f"%{codigo.strip()}%"))
    return paginar(sesion, consulta, parametros)


def listar_novedades(
    sesion: Session,
    vehiculo_id: int,
    parametros: ParametrosPagina,
    estado: EstadoNovedad | None = None,
) -> ResultadoPagina:
    """Historial de novedades de una unidad, de la más reciente a la más antigua."""
    if sesion.get(Vehiculo, vehiculo_id) is None:
        raise VehiculoNoEncontrado()
    consulta = (
        select(NovedadVehiculo)
        .where(NovedadVehiculo.vehiculo_id == vehiculo_id)
        .order_by(NovedadVehiculo.creado_en.desc(), NovedadVehiculo.id.desc())
    )
    if estado is not None:
        consulta = consulta.where(NovedadVehiculo.estado == estado)
    return paginar(sesion, consulta, parametros)


def reportar_novedad(
    sesion: Session,
    vehiculo_id: int,
    datos: NovedadCrear,
    usuario: Usuario,
    *,
    hoy: date | None = None,
    momento: datetime | None = None,
) -> ResultadoOperacion:
    """Registra una novedad. Si es crítica, la unidad pasa a mantenimiento automáticamente.

    Pueden reportar el administrador, el operador y el domiciliario. Los alquileres
    vigentes de la unidad NO se cancelan: se devuelven en ``alquileres_afectados`` para que
    el personal decida qué hacer con cada uno.
    """
    _exigir_rol(usuario, ROLES_QUE_REPORTAN)
    vehiculo = bloquear_vehiculo(sesion, vehiculo_id)
    if vehiculo.estado == EstadoVehiculo.VENDIDO:
        raise VehiculoVendido()

    novedad = NovedadVehiculo(
        vehiculo_id=vehiculo.id,
        tipo=datos.tipo,
        descripcion=datos.descripcion,
        es_critica=datos.es_critica,
        reportada_por_id=usuario.id,
    )
    sesion.add(novedad)
    sesion.flush()

    afectados: list[Alquiler] = []
    if datos.es_critica:
        if vehiculo.estado != EstadoVehiculo.MANTENIMIENTO:
            motivo = f"Novedad crítica #{novedad.id} ({datos.tipo.value})"
            cambiar_estado_vehiculo(sesion, vehiculo, EstadoVehiculo.MANTENIMIENTO, usuario, motivo)
        consulta = consulta_alquileres_vigentes(
            vehiculo.id, hoy or fechas.hoy(), momento or fechas.ahora()
        )
        afectados = list(sesion.scalars(consulta))
    sesion.commit()
    return ResultadoOperacion(vehiculo, novedad, afectados)


def inactivar_vehiculo(
    sesion: Session,
    vehiculo_id: int,
    motivo: str,
    usuario: Usuario,
    *,
    hoy: date | None = None,
    momento: datetime | None = None,
) -> ResultadoOperacion:
    """HU-09: saca la unidad de servicio con un motivo. Desaparece del catálogo al instante.

    Solo el taller (administrador u operador); el domiciliario reporta novedades.
    """
    _exigir_rol(usuario, ROLES_DE_TALLER)
    datos = NovedadCrear(tipo=TipoNovedad.MANTENIMIENTO, descripcion=motivo, es_critica=True)
    return reportar_novedad(sesion, vehiculo_id, datos, usuario, hoy=hoy, momento=momento)


def _verificar_que_puede_volver(
    sesion: Session, vehiculo: Vehiculo, novedad_que_se_cierra: int
) -> None:
    """Lanza un error con la causa concreta si la unidad no puede volver (CLAUDE.md 7.2)."""
    if not es_transicion_valida(vehiculo.estado, EstadoVehiculo.DISPONIBLE):
        raise TransicionInvalida(
            f"La unidad está en '{vehiculo.estado}', no en mantenimiento: no hay nada que "
            "devolver a servicio."
        )
    # Solo bloquean las críticas: las no críticas quedan como registro (p. ej., un rayón).
    otras_criticas = sesion.scalar(
        select(func.count()).where(
            NovedadVehiculo.vehiculo_id == vehiculo.id,
            NovedadVehiculo.estado == EstadoNovedad.ABIERTA,
            NovedadVehiculo.es_critica,
            NovedadVehiculo.id != novedad_que_se_cierra,
        )
    )
    if otras_criticas:
        raise NoPuedeVolverAServicio(
            f"La unidad tiene {otras_criticas} novedad(es) crítica(s) abierta(s) además de "
            "esta. Ciérralas antes de devolverla a servicio."
        )
    if sesion.scalars(consulta_alquiler_en_curso(vehiculo.id)).first() is not None:
        raise NoPuedeVolverAServicio(
            "La unidad tiene un alquiler en curso. Registra primero la devolución."
        )
    if sesion.scalars(consulta_domicilios_sin_finalizar(vehiculo.id)).first() is not None:
        raise NoPuedeVolverAServicio("La unidad participa en un domicilio sin finalizar.")


def cerrar_novedad(
    sesion: Session,
    vehiculo_id: int,
    novedad_id: int,
    datos: CierreNovedad,
    usuario: Usuario,
) -> ResultadoOperacion:
    """Cierra una novedad con su solución y, si se pide, devuelve la unidad a servicio.

    Solo un operador o un administrador. Con ``devolver_a_servicio`` todo se valida antes
    de tocar nada: si la unidad no puede volver, la novedad tampoco se cierra.
    """
    _exigir_rol(usuario, ROLES_DE_TALLER)
    vehiculo = bloquear_vehiculo(sesion, vehiculo_id)
    novedad = sesion.scalars(
        select(NovedadVehiculo)
        .where(NovedadVehiculo.id == novedad_id, NovedadVehiculo.vehiculo_id == vehiculo.id)
        .with_for_update()
    ).one_or_none()
    if novedad is None:
        raise NovedadNoEncontrada()
    if novedad.estado == EstadoNovedad.CERRADA:
        raise NovedadYaCerrada()
    if datos.devolver_a_servicio:
        _verificar_que_puede_volver(sesion, vehiculo, novedad.id)

    novedad.estado = EstadoNovedad.CERRADA
    novedad.cerrada_por_id = usuario.id
    novedad.cerrada_en = fechas.ahora()
    novedad.solucion = datos.solucion
    if datos.devolver_a_servicio:
        motivo = f"Cierre de la novedad #{novedad.id}"
        cambiar_estado_vehiculo(sesion, vehiculo, EstadoVehiculo.DISPONIBLE, usuario, motivo)
    sesion.commit()
    return ResultadoOperacion(vehiculo, novedad, [])
