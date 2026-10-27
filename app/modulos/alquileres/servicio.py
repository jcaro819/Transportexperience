"""Reglas de negocio de los alquileres (HU-03, SRS 3.1.1 y 3.3.3).

Cómo se garantiza que un vehículo no se reserve dos veces (CLAUDE.md 7.1):

1. **Bloqueo de fila.** Toda operación empieza con ``SELECT ... FOR UPDATE`` sobre las
   unidades que va a tocar, dentro de la misma transacción del cambio. Crear una reserva
   bloquea *todas* las unidades del modelo, siempre en orden de ``id``: así dos reservas
   simultáneas del mismo modelo se atienden una detrás de otra y nunca se bloquean en
   cruz (sin *deadlocks*). La segunda espera, y cuando entra ya ve la reserva de la primera.
2. **Restricción de exclusión.** Aunque el código tuviera un error, Postgres rechaza dos
   alquileres activos del mismo vehículo con fechas cruzadas
   (``ex_alquileres_sin_solapamiento``).
3. **Pendientes vencidos.** Con las unidades bloqueadas, y antes de reservar, los
   ``pendiente_pago`` cuyo bloqueo de 15 minutos ya pasó se marcan ``expirado``. No hay
   tareas en segundo plano: una reserva abandonada se libera cuando alguien la necesita.

Todas las operaciones validan antes de modificar y confirman al final. Si algo falla, el
alquiler y la unidad quedan exactamente como estaban (SRS 3.3.4).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.auditoria import registrar_auditoria
from app.comun import fechas
from app.comun.errores import PermisoDenegado
from app.comun.paginacion import ParametrosPagina, ResultadoPagina, paginar
from app.modulos.alquileres.estados import validar_transicion
from app.modulos.alquileres.excepciones import (
    AlquilerNoCancelable,
    AlquilerNoEncontrado,
    DuracionExcedida,
    FueraDeLasFechasDelAlquiler,
    ReasignacionInvalida,
    ReservaExpirada,
    SinUnidadesDisponibles,
    VehiculoNoListoParaEntrega,
)
from app.modulos.alquileres.modelos import Alquiler, EstadoAlquiler
from app.modulos.inventario.excepciones import FechasInvalidas, ModeloNoSeAlquila
from app.modulos.inventario.modelos import EstadoVehiculo, Vehiculo
from app.modulos.inventario.servicio import (
    bloquear_vehiculo,
    cambiar_estado_vehiculo,
    consulta_unidades_libres,
    obtener_modelo_visible,
)
from app.modulos.pagos import servicio as pagos
from app.modulos.pagos.modelos import EstadoPago, Pago
from app.modulos.pagos.pasarela import PasarelaPagos
from app.modulos.usuarios.modelos import Rol, Usuario
from app.parametros import MAX_DIAS_ALQUILER, obtener_entero

# Bloqueo temporal mientras el cliente paga (decisión del 29/09/2026, HU-03).
MINUTOS_BLOQUEO = 15

# Ven y atienden todos los alquileres: entregan y reciben vehículos.
ROLES_DE_MOSTRADOR = frozenset({Rol.ADMINISTRADOR, Rol.OPERADOR})

# Alquileres que todavía pueden moverse a otra unidad: aún no se ha entregado el vehículo.
_ESTADOS_REASIGNABLES = (EstadoAlquiler.PENDIENTE_PAGO, EstadoAlquiler.CONFIRMADO)


@dataclass(frozen=True)
class ResultadoPago:
    alquiler: Alquiler
    pago: Pago


# --- Lógica pura: sin base de datos ---------------------------------------------------------


def calcular_subtotal(tarifa_diaria: int, inicio: date, fin: date) -> int:
    """Valor del alquiler en pesos: días inclusivos por tarifa. Del 5 al 7 son 3 días."""
    return ((fin - inicio).days + 1) * tarifa_diaria


def validar_fechas(inicio: date, fin: date, hoy: date, max_dias: int) -> None:
    """Rechaza fechas pasadas, rangos al revés y alquileres más largos que ``max_dias``."""
    if inicio < hoy:
        raise FechasInvalidas("La fecha de inicio ya pasó.")
    if fin < inicio:
        raise FechasInvalidas("La fecha de fin es anterior a la de inicio.")
    dias = (fin - inicio).days + 1
    if dias > max_dias:
        raise DuracionExcedida(
            f"El alquiler sería de {dias} días y el máximo permitido es de {max_dias}."
        )


def esta_vencido(alquiler: Alquiler, momento: datetime) -> bool:
    """Un ``pendiente_pago`` cuyo bloqueo de 15 minutos ya pasó."""
    return (
        alquiler.estado == EstadoAlquiler.PENDIENTE_PAGO
        and alquiler.expira_en is not None
        and alquiler.expira_en <= momento
    )


def estado_vigente(alquiler: Alquiler, momento: datetime) -> EstadoAlquiler:
    """El estado que se le muestra al usuario.

    Un pendiente vencido se muestra ``expirado`` aunque nadie lo haya marcado todavía:
    una consulta no escribe en la base, pero tampoco debe mostrar vigente lo que ya venció.
    """
    return EstadoAlquiler.EXPIRADO if esta_vencido(alquiler, momento) else alquiler.estado


# --- Piezas internas -------------------------------------------------------------------------


def _exigir_rol(usuario: Usuario, permitidos: frozenset[Rol]) -> None:
    # Las rutas ya lo exigen; el servicio lo repite para que ninguna llamada futura lo salte.
    if usuario.rol not in permitidos:
        raise PermisoDenegado()


def _cambiar_estado(
    sesion: Session,
    alquiler: Alquiler,
    nuevo: EstadoAlquiler,
    usuario: Usuario | None,
    motivo: str | None = None,
) -> None:
    """Único camino para cambiar el estado de un alquiler: valida la transición y la audita."""
    anterior = alquiler.estado
    validar_transicion(anterior, nuevo)
    alquiler.estado = nuevo
    if nuevo != EstadoAlquiler.PENDIENTE_PAGO:
        alquiler.expira_en = None  # el bloqueo temporal solo existe mientras se paga
    despues = {"estado": nuevo.value}
    if motivo:
        despues["motivo"] = motivo
    registrar_auditoria(
        sesion,
        usuario_id=usuario.id if usuario else None,
        accion="cambiar_estado",
        entidad="alquileres",
        entidad_id=alquiler.id,
        antes={"estado": anterior.value},
        despues=despues,
    )


def expirar_vencidos(
    sesion: Session, momento: datetime, vehiculo_ids: Sequence[int] | None = None
) -> int:
    """Marca ``expirado`` los ``pendiente_pago`` vencidos y devuelve cuántos expiraron.

    Con ``vehiculo_ids``, solo los de esas unidades, que quien llama ya debe tener
    bloqueadas. Sin él, todos (para un barrido manual). No hace commit.
    """
    consulta = (
        select(Alquiler)
        .where(
            Alquiler.estado == EstadoAlquiler.PENDIENTE_PAGO,
            Alquiler.expira_en <= momento,
        )
        .order_by(Alquiler.id)
        .with_for_update()
    )
    if vehiculo_ids is not None:
        consulta = consulta.where(Alquiler.vehiculo_id.in_(vehiculo_ids))
    vencidos = sesion.scalars(consulta).all()
    for alquiler in vencidos:
        # usuario=None: lo hace el sistema, no una persona.
        _cambiar_estado(sesion, alquiler, EstadoAlquiler.EXPIRADO, None, "Bloqueo vencido")
    sesion.flush()
    return len(vencidos)


def _bloquear_unidades_del_modelo(sesion: Session, modelo_id: int) -> list[Vehiculo]:
    """``FOR UPDATE`` sobre todas las unidades del modelo, en orden de ``id``.

    El orden fijo es lo que evita los *deadlocks*: dos transacciones que bloquean en el
    mismo orden nunca quedan esperándose la una a la otra.
    """
    return list(
        sesion.scalars(
            select(Vehiculo)
            .where(Vehiculo.modelo_id == modelo_id)
            .order_by(Vehiculo.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )


def _libres_entre(
    sesion: Session,
    unidades: Sequence[Vehiculo],
    inicio: date,
    fin: date,
    hoy: date,
    momento: datetime,
) -> list[Vehiculo]:
    """Las de ``unidades`` libres durante todo [inicio, fin], en el mismo orden."""
    if not unidades:
        return []
    libres = consulta_unidades_libres(inicio, fin, hoy, momento).with_only_columns(Vehiculo.id)
    ids_libres = set(sesion.scalars(libres.where(Vehiculo.id.in_([u.id for u in unidades]))))
    return [u for u in unidades if u.id in ids_libres]


def _bloquear_alquiler(sesion: Session, alquiler_id: int) -> Alquiler:
    """Bloquea la unidad del alquiler (regla 1 de CLAUDE.md 7.1) y luego el alquiler."""
    vehiculo_id = sesion.scalar(select(Alquiler.vehiculo_id).where(Alquiler.id == alquiler_id))
    if vehiculo_id is None:
        raise AlquilerNoEncontrado()
    bloquear_vehiculo(sesion, vehiculo_id)
    alquiler = sesion.scalars(
        select(Alquiler)
        .where(Alquiler.id == alquiler_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if alquiler.vehiculo_id != vehiculo_id:
        # Una reasignación lo movió de unidad mientras esperábamos: bloquea también la nueva.
        bloquear_vehiculo(sesion, alquiler.vehiculo_id)
    return alquiler


def _del_cliente(alquiler: Alquiler, cliente: Usuario) -> None:
    # A otro cliente se le dice "no existe", no "no es tuyo": no se revela qué ids existen.
    if alquiler.cliente_id != cliente.id:
        raise AlquilerNoEncontrado()


def _expirar_y_avisar(sesion: Session, alquiler: Alquiler) -> None:
    """Marca expirado el pendiente vencido, lo confirma y avisa al cliente."""
    _cambiar_estado(sesion, alquiler, EstadoAlquiler.EXPIRADO, None, "Bloqueo vencido")
    sesion.commit()
    raise ReservaExpirada()


# --- Cliente: reservar, pagar, cancelar, consultar ------------------------------------------


def crear_alquiler(
    sesion: Session,
    cliente: Usuario,
    modelo_id: int,
    fecha_inicio: date,
    fecha_fin: date,
    *,
    hoy: date | None = None,
    momento: datetime | None = None,
) -> Alquiler:
    """Reserva una unidad libre del modelo y la bloquea 15 minutos mientras se paga.

    El cliente escoge el modelo en el catálogo; el sistema asigna la primera unidad libre
    en esas fechas. Precio: la tarifa diaria vigente del modelo por los días inclusivos.
    """
    _exigir_rol(cliente, frozenset({Rol.CLIENTE}))
    hoy = hoy or fechas.hoy()
    momento = momento or fechas.ahora()
    validar_fechas(fecha_inicio, fecha_fin, hoy, obtener_entero(sesion, MAX_DIAS_ALQUILER))
    modelo = obtener_modelo_visible(sesion, modelo_id)
    if modelo.tarifa_diaria is None:
        raise ModeloNoSeAlquila()

    unidades = _bloquear_unidades_del_modelo(sesion, modelo.id)
    expirar_vencidos(sesion, momento, [u.id for u in unidades])
    libres = _libres_entre(sesion, unidades, fecha_inicio, fecha_fin, hoy, momento)
    if not libres:
        raise SinUnidadesDisponibles()

    subtotal = calcular_subtotal(modelo.tarifa_diaria, fecha_inicio, fecha_fin)
    alquiler = Alquiler(
        cliente_id=cliente.id,
        vehiculo_id=libres[0].id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        tarifa_diaria=modelo.tarifa_diaria,
        subtotal=subtotal,
        valor_envio=0,  # el domicilio se suma con HU-06
        total=subtotal,
        estado=EstadoAlquiler.PENDIENTE_PAGO,
        expira_en=momento + timedelta(minutes=MINUTOS_BLOQUEO),
    )
    try:
        with sesion.begin_nested():
            sesion.add(alquiler)
            sesion.flush()
    except IntegrityError as error:
        # Con las unidades bloqueadas no debería pasar; si pasa, la base tenía razón.
        if "ex_alquileres_sin_solapamiento" in str(error.orig):
            raise SinUnidadesDisponibles() from error
        raise
    registrar_auditoria(
        sesion,
        usuario_id=cliente.id,
        accion="crear",
        entidad="alquileres",
        entidad_id=alquiler.id,
        despues={
            "vehiculo_id": alquiler.vehiculo_id,
            "fecha_inicio": fecha_inicio.isoformat(),
            "fecha_fin": fecha_fin.isoformat(),
            "total": alquiler.total,
        },
    )
    sesion.commit()
    return alquiler


def pagar_alquiler(
    sesion: Session,
    alquiler_id: int,
    cliente: Usuario,
    metodo_codigo: str,
    pasarela: PasarelaPagos,
    *,
    momento: datetime | None = None,
) -> ResultadoPago:
    """Cobra el total de una reserva pendiente con la pasarela configurada.

    - Aprobado: el alquiler pasa a ``confirmado`` y el vehículo queda reservado sin plazo.
    - Rechazado: el alquiler sigue ``pendiente_pago`` y el cliente puede reintentar
      mientras no venza el bloqueo.
    - Pendiente (Wompi, HU-05): la confirmación llegará por el webhook, que llamará a
      ``confirmar_pago``.
    """
    momento = momento or fechas.ahora()
    alquiler = _bloquear_alquiler(sesion, alquiler_id)
    _del_cliente(alquiler, cliente)
    if esta_vencido(alquiler, momento):
        _expirar_y_avisar(sesion, alquiler)
    validar_transicion(alquiler.estado, EstadoAlquiler.CONFIRMADO)
    metodo = pagos.obtener_metodo_activo(sesion, metodo_codigo)

    pago = pagos.cobrar_alquiler(sesion, pasarela, alquiler.id, alquiler.total, metodo, momento)
    if pago.estado == EstadoPago.APROBADO:
        confirmar_pago(sesion, alquiler, cliente)
    sesion.commit()
    return ResultadoPago(alquiler, pago)


def confirmar_pago(sesion: Session, alquiler: Alquiler, usuario: Usuario | None) -> None:
    """Pasa a ``confirmado`` un alquiler cuyo pago se aprobó. No hace commit.

    La fila del alquiler (y la de su unidad) deben estar bloqueadas. HU-05 la llamará
    desde el webhook de la pasarela.
    """
    _cambiar_estado(sesion, alquiler, EstadoAlquiler.CONFIRMADO, usuario, "Pago aprobado")


def cancelar_alquiler(
    sesion: Session,
    alquiler_id: int,
    cliente: Usuario,
    motivo: str | None = None,
    *,
    momento: datetime | None = None,
) -> Alquiler:
    """El cliente desiste de una reserva. Solo mientras está en ``pendiente_pago``.

    Un alquiler ya pagado no se cancela desde aquí: exige devolver el dinero con un pago de
    compensación, y eso lo gestiona el administrador (HU-05).
    """
    momento = momento or fechas.ahora()
    alquiler = _bloquear_alquiler(sesion, alquiler_id)
    _del_cliente(alquiler, cliente)
    if esta_vencido(alquiler, momento):
        _expirar_y_avisar(sesion, alquiler)
    if alquiler.estado != EstadoAlquiler.PENDIENTE_PAGO:
        raise AlquilerNoCancelable()
    alquiler.motivo_cancelacion = motivo
    _cambiar_estado(sesion, alquiler, EstadoAlquiler.CANCELADO, cliente, motivo)
    sesion.commit()
    return alquiler


def _con_vehiculo():
    return joinedload(Alquiler.vehiculo).joinedload(Vehiculo.modelo)


def _filtro_estado(estado: EstadoAlquiler, momento: datetime) -> ColumnElement[bool]:
    """Filtro por el estado *vigente* (ver ``estado_vigente``), no por el guardado."""
    vencido = and_(Alquiler.estado == EstadoAlquiler.PENDIENTE_PAGO, Alquiler.expira_en <= momento)
    if estado == EstadoAlquiler.EXPIRADO:
        return or_(Alquiler.estado == EstadoAlquiler.EXPIRADO, vencido)
    if estado == EstadoAlquiler.PENDIENTE_PAGO:
        return and_(Alquiler.estado == estado, Alquiler.expira_en > momento)
    return Alquiler.estado == estado


def listar_alquileres(
    sesion: Session,
    parametros: ParametrosPagina,
    *,
    cliente_id: int | None = None,
    vehiculo_id: int | None = None,
    estado: EstadoAlquiler | None = None,
    momento: datetime | None = None,
) -> ResultadoPagina:
    """Alquileres del más reciente al más antiguo. El cliente solo pide los suyos."""
    momento = momento or fechas.ahora()
    consulta = select(Alquiler).options(_con_vehiculo()).order_by(Alquiler.id.desc())
    if cliente_id is not None:
        consulta = consulta.where(Alquiler.cliente_id == cliente_id)
    if vehiculo_id is not None:
        consulta = consulta.where(Alquiler.vehiculo_id == vehiculo_id)
    if estado is not None:
        consulta = consulta.where(_filtro_estado(estado, momento))
    return paginar(sesion, consulta, parametros)


def obtener_alquiler(sesion: Session, alquiler_id: int, usuario: Usuario) -> Alquiler:
    """Un alquiler. El cliente solo ve los suyos; el mostrador, todos."""
    alquiler = sesion.scalars(
        select(Alquiler).where(Alquiler.id == alquiler_id).options(_con_vehiculo())
    ).one_or_none()
    if alquiler is None:
        raise AlquilerNoEncontrado()
    if usuario.rol == Rol.CLIENTE:
        _del_cliente(alquiler, usuario)
    else:
        _exigir_rol(usuario, ROLES_DE_MOSTRADOR)
    return alquiler


# --- Mostrador: entregar y recibir el vehículo ----------------------------------------------


def entregar_vehiculo(
    sesion: Session, alquiler_id: int, usuario: Usuario, *, hoy: date | None = None
) -> Alquiler:
    """El operador entrega la unidad al cliente: ``confirmado`` → ``en_curso``.

    La unidad pasa de ``disponible`` a ``alquilado``. Se entrega entre la fecha de inicio y
    la de fin del alquiler, y solo si la unidad está físicamente disponible.
    """
    _exigir_rol(usuario, ROLES_DE_MOSTRADOR)
    hoy = hoy or fechas.hoy()
    alquiler = _bloquear_alquiler(sesion, alquiler_id)
    validar_transicion(alquiler.estado, EstadoAlquiler.EN_CURSO)
    if not alquiler.fecha_inicio <= hoy <= alquiler.fecha_fin:
        raise FueraDeLasFechasDelAlquiler(
            f"El alquiler va del {alquiler.fecha_inicio} al {alquiler.fecha_fin} y hoy es {hoy}."
        )
    vehiculo = alquiler.vehiculo
    if vehiculo.estado == EstadoVehiculo.MANTENIMIENTO:
        raise VehiculoNoListoParaEntrega(
            f"La unidad {vehiculo.codigo} está en mantenimiento. Reasigna el alquiler a otra "
            "unidad libre del mismo modelo."
        )
    if vehiculo.estado == EstadoVehiculo.ALQUILADO:
        raise VehiculoNoListoParaEntrega(
            f"La unidad {vehiculo.codigo} sigue en manos del cliente anterior. Registra "
            "primero la devolución de ese alquiler."
        )
    if vehiculo.estado != EstadoVehiculo.DISPONIBLE:
        raise VehiculoNoListoParaEntrega(
            f"La unidad {vehiculo.codigo} está en '{vehiculo.estado}' y no se puede entregar."
        )
    motivo = f"Entrega del alquiler #{alquiler.id}"
    cambiar_estado_vehiculo(sesion, vehiculo, EstadoVehiculo.ALQUILADO, usuario, motivo)
    _cambiar_estado(sesion, alquiler, EstadoAlquiler.EN_CURSO, usuario)
    sesion.commit()
    return alquiler


def recibir_vehiculo(sesion: Session, alquiler_id: int, usuario: Usuario) -> Alquiler:
    """El operador recibe la unidad de vuelta: ``en_curso`` → ``finalizado``.

    Si la unidad sigue ``alquilado``, vuelve a ``disponible``. Si entró en mantenimiento
    durante el alquiler (una novedad crítica), el alquiler se finaliza igual pero la unidad
    **se queda en mantenimiento** hasta que el taller cierre su novedad (CLAUDE.md, sección 4).
    """
    _exigir_rol(usuario, ROLES_DE_MOSTRADOR)
    alquiler = _bloquear_alquiler(sesion, alquiler_id)
    validar_transicion(alquiler.estado, EstadoAlquiler.FINALIZADO)
    vehiculo = alquiler.vehiculo
    if vehiculo.estado == EstadoVehiculo.ALQUILADO:
        motivo = f"Devolución del alquiler #{alquiler.id}"
        cambiar_estado_vehiculo(sesion, vehiculo, EstadoVehiculo.DISPONIBLE, usuario, motivo)
    _cambiar_estado(sesion, alquiler, EstadoAlquiler.FINALIZADO, usuario)
    sesion.commit()
    return alquiler


# --- Administrador: alquileres en riesgo y reasignación -------------------------------------


def listar_en_riesgo(
    sesion: Session, parametros: ParametrosPagina, *, momento: datetime | None = None
) -> ResultadoPagina:
    """Alquileres aún no entregados cuya unidad está en mantenimiento.

    Son los que hay que reasignar, esperar o cancelar con devolución; esta lista existe
    para que nadie los olvide. Del que empieza primero al que empieza último.
    """
    momento = momento or fechas.ahora()
    vigente = or_(
        Alquiler.estado == EstadoAlquiler.CONFIRMADO,
        and_(Alquiler.estado == EstadoAlquiler.PENDIENTE_PAGO, Alquiler.expira_en > momento),
    )
    consulta = (
        select(Alquiler)
        .join(Alquiler.vehiculo)
        .where(vigente, Vehiculo.estado == EstadoVehiculo.MANTENIMIENTO)
        .options(_con_vehiculo())
        .order_by(Alquiler.fecha_inicio, Alquiler.id)
    )
    return paginar(sesion, consulta, parametros)


def reasignar_alquiler(
    sesion: Session,
    alquiler_id: int,
    usuario: Usuario,
    vehiculo_id: int | None = None,
    *,
    hoy: date | None = None,
    momento: datetime | None = None,
) -> Alquiler:
    """Mueve un alquiler aún no entregado a otra unidad libre del mismo modelo.

    Mismo precio y mismas fechas. Con ``vehiculo_id`` se usa esa unidad; sin él, la primera
    libre. Las dos unidades quedan bloqueadas en la misma transacción. Solo el
    administrador (decisión del Sprint 2: reasignación asistida, nunca automática).
    """
    _exigir_rol(usuario, frozenset({Rol.ADMINISTRADOR}))
    hoy = hoy or fechas.hoy()
    momento = momento or fechas.ahora()
    actual = sesion.get(Alquiler, alquiler_id)
    if actual is None:
        raise AlquilerNoEncontrado()

    # Mismo orden de bloqueo que crear_alquiler: todas las unidades del modelo, por id.
    unidades = _bloquear_unidades_del_modelo(sesion, actual.vehiculo.modelo_id)
    alquiler = sesion.scalars(
        select(Alquiler)
        .where(Alquiler.id == alquiler_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if alquiler.vehiculo_id not in {u.id for u in unidades}:
        raise ReasignacionInvalida("El alquiler cambió mientras se procesaba. Inténtalo de nuevo.")
    if esta_vencido(alquiler, momento):
        _expirar_y_avisar(sesion, alquiler)
    if alquiler.estado not in _ESTADOS_REASIGNABLES:
        raise ReasignacionInvalida(
            f"El alquiler está en '{alquiler.estado}': solo se reasignan los que aún no se "
            "han entregado."
        )

    anterior = alquiler.vehiculo_id
    otras = [u for u in unidades if u.id != anterior]
    if vehiculo_id is not None:
        otras = [u for u in otras if u.id == vehiculo_id]
        if not otras:
            raise ReasignacionInvalida(
                "La unidad elegida no existe, es la misma del alquiler o es de otro modelo."
            )
    libres = _libres_entre(sesion, otras, alquiler.fecha_inicio, alquiler.fecha_fin, hoy, momento)
    if not libres:
        raise SinUnidadesDisponibles(
            "No hay otra unidad de este modelo libre en las fechas del alquiler."
        )

    alquiler.vehiculo_id = libres[0].id
    sesion.flush()
    registrar_auditoria(
        sesion,
        usuario_id=usuario.id,
        accion="reasignar",
        entidad="alquileres",
        entidad_id=alquiler.id,
        antes={"vehiculo_id": anterior},
        despues={"vehiculo_id": alquiler.vehiculo_id},
    )
    sesion.commit()
    sesion.refresh(alquiler)
    return alquiler
