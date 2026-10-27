"""Reglas de negocio de los domicilios (HU-06, SRS 3.1.3 y 3.6).

Decisiones del Sprint 3:

1. **El domicilio se agrega antes de pagar**: a un alquiler o compra en ``pendiente_pago``
   y sin un pago en curso. El total de la operación se recalcula con la tarifa fija de la
   zona; un solo pago cubre todo. Una dirección fuera de cobertura **se bloquea**.
2. **La asignación la hace el administrador o el operador a mano**, eligiendo de la lista
   de domiciliarios disponibles (sin entregas en ruta). Sin asignación automática.

La zona se decide con ``geometria.punto_en_poligono`` (función propia, sin PostGIS). Si un
punto cae en el borde entre dos zonas, se cobra la tarifa más baja.

Orden de bloqueo (el mismo de todo el sistema): vehículos, luego la operación (alquiler o
venta), luego el domicilio.
"""

import secrets
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload

from app.auditoria import registrar_auditoria
from app.comun import fechas
from app.comun.errores import PermisoDenegado
from app.comun.paginacion import ParametrosPagina, ResultadoPagina, paginar
from app.modulos.alquileres import servicio as alquileres
from app.modulos.alquileres.consultas import consulta_vehiculos_ocupados
from app.modulos.alquileres.modelos import Alquiler, EstadoAlquiler
from app.modulos.domicilios.consultas import ESTADOS_EN_RUTA
from app.modulos.domicilios.estados import validar_transicion
from app.modulos.domicilios.excepciones import (
    DomiciliarioNoDisponible,
    DomicilioNoEncontrado,
    DomicilioSinPagar,
    FueraDeCobertura,
    OperacionNoAdmiteDomicilio,
    VehiculoDeTransporteNoDisponible,
    YaTieneDomicilio,
)
from app.modulos.domicilios.geometria import punto_en_poligono
from app.modulos.domicilios.liberacion import cambiar_estado_domicilio, domicilio_vigente
from app.modulos.domicilios.modelos import (
    Domicilio,
    EstadoDomicilio,
    HistorialEstadoDomicilio,
    ZonaCobertura,
)
from app.modulos.inventario.modelos import EstadoVehiculo
from app.modulos.inventario.servicio import bloquear_vehiculo, cambiar_estado_vehiculo
from app.modulos.pagos import servicio as pagos
from app.modulos.pagos.excepciones import PagoEnCurso
from app.modulos.usuarios.modelos import Rol, Usuario
from app.modulos.ventas import servicio as ventas
from app.modulos.ventas.modelos import EstadoVenta, Venta

ROLES_DE_DESPACHO = frozenset({Rol.ADMINISTRADOR, Rol.OPERADOR})

# Sin letras ni números que se confundan al dictarlos (O/0, I/1).
_ALFABETO_RASTREO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


@dataclass(frozen=True)
class DomicilioConTotales:
    domicilio: Domicilio
    valor_envio: int
    total: int


# --- Cobertura ------------------------------------------------------------------------------


def listar_zonas(sesion: Session, parametros: ParametrosPagina) -> ResultadoPagina:
    """Zonas de cobertura activas, para dibujarlas en el mapa."""
    consulta = select(ZonaCobertura).where(ZonaCobertura.activa).order_by(ZonaCobertura.nombre)
    return paginar(sesion, consulta, parametros)


def zona_para_punto(sesion: Session, latitud: Decimal, longitud: Decimal) -> ZonaCobertura:
    """La zona activa que cubre el punto; en un borde compartido, la de tarifa más baja."""
    zonas = sesion.scalars(
        select(ZonaCobertura)
        .where(ZonaCobertura.activa)
        .order_by(ZonaCobertura.tarifa_envio, ZonaCobertura.id)
    ).all()
    for zona in zonas:
        if punto_en_poligono(float(latitud), float(longitud), zona.poligono):
            return zona
    raise FueraDeCobertura()


# --- Cliente: solicitar y quitar el domicilio -----------------------------------------------


def _codigo_rastreo(sesion: Session) -> str:
    while True:
        codigo = "TX-" + "".join(secrets.choice(_ALFABETO_RASTREO) for _ in range(8))
        if sesion.scalar(select(Domicilio.id).where(Domicilio.codigo_rastreo == codigo)) is None:
            return codigo


def _operacion_del_cliente(
    sesion: Session, cliente: Usuario, momento: datetime, *, alquiler_id=None, venta_id=None
) -> Alquiler | Venta:
    """Bloquea la operación y exige que admita cambios en el domicilio (decisión 1)."""
    if alquiler_id is not None:
        operacion = alquileres.bloquear_del_cliente(sesion, alquiler_id, cliente, momento)
        pendiente = operacion.estado == EstadoAlquiler.PENDIENTE_PAGO
    else:
        operacion = ventas.bloquear_del_cliente(sesion, venta_id, cliente, momento)
        pendiente = operacion.estado == EstadoVenta.PENDIENTE_PAGO
    if not pendiente:
        raise OperacionNoAdmiteDomicilio()
    # Con un pago en curso el total no puede cambiar: el banco cobra el monto ya enviado.
    if pagos.hay_cobro_pendiente(sesion, alquiler_id=alquiler_id, venta_id=venta_id):
        raise PagoEnCurso()
    return operacion


def _cambiar_envio(operacion: Alquiler | Venta, valor_envio: int) -> None:
    operacion.valor_envio = valor_envio
    operacion.total = operacion.subtotal + valor_envio


def solicitar_domicilio(
    sesion: Session,
    cliente: Usuario,
    *,
    alquiler_id: int | None,
    venta_id: int | None,
    direccion: str,
    indicaciones: str | None,
    latitud: Decimal,
    longitud: Decimal,
    momento: datetime | None = None,
) -> DomicilioConTotales:
    """Agrega el domicilio a una operación sin pagar y suma la tarifa de la zona al total."""
    if cliente.rol != Rol.CLIENTE:
        raise PermisoDenegado()
    momento = momento or fechas.ahora()
    zona = zona_para_punto(sesion, latitud, longitud)  # fuera de cobertura: se bloquea

    operacion = _operacion_del_cliente(
        sesion, cliente, momento, alquiler_id=alquiler_id, venta_id=venta_id
    )
    if domicilio_vigente(sesion, alquiler_id=alquiler_id, venta_id=venta_id) is not None:
        raise YaTieneDomicilio()

    domicilio = Domicilio(
        codigo_rastreo=_codigo_rastreo(sesion),
        cliente_id=cliente.id,
        alquiler_id=alquiler_id,
        venta_id=venta_id,
        zona_id=zona.id,
        direccion=direccion,
        indicaciones=indicaciones,
        latitud=latitud,
        longitud=longitud,
        estado=EstadoDomicilio.PENDIENTE,
    )
    sesion.add(domicilio)
    sesion.flush()
    sesion.add(
        HistorialEstadoDomicilio(
            domicilio_id=domicilio.id,
            estado_anterior=None,
            estado_nuevo=EstadoDomicilio.PENDIENTE,
            cambiado_por_id=cliente.id,
        )
    )
    anterior = operacion.total
    _cambiar_envio(operacion, zona.tarifa_envio)
    registrar_auditoria(
        sesion,
        usuario_id=cliente.id,
        accion="agregar_domicilio",
        entidad="alquileres" if alquiler_id else "ventas",
        entidad_id=operacion.id,
        antes={"total": anterior},
        despues={
            "domicilio_id": domicilio.id,
            "valor_envio": zona.tarifa_envio,
            "total": operacion.total,
        },
    )
    sesion.commit()
    return DomicilioConTotales(domicilio, operacion.valor_envio, operacion.total)


def cancelar_domicilio(
    sesion: Session, domicilio_id: int, cliente: Usuario, *, momento: datetime | None = None
) -> DomicilioConTotales:
    """El cliente quita el domicilio antes de pagar: el envío sale del total."""
    momento = momento or fechas.ahora()
    datos = sesion.execute(
        select(Domicilio.cliente_id, Domicilio.alquiler_id, Domicilio.venta_id).where(
            Domicilio.id == domicilio_id
        )
    ).one_or_none()
    if datos is None or datos.cliente_id != cliente.id:
        raise DomicilioNoEncontrado()
    operacion = _operacion_del_cliente(
        sesion, cliente, momento, alquiler_id=datos.alquiler_id, venta_id=datos.venta_id
    )
    domicilio = domicilio_vigente(sesion, alquiler_id=datos.alquiler_id, venta_id=datos.venta_id)
    if domicilio is None or domicilio.id != domicilio_id:
        raise DomicilioNoEncontrado("Ese domicilio ya fue cancelado.")
    domicilio.motivo_cancelacion = "El cliente quitó el domicilio antes de pagar."
    cambiar_estado_domicilio(sesion, domicilio, EstadoDomicilio.CANCELADO, cliente.id)
    anterior = operacion.total
    _cambiar_envio(operacion, 0)
    registrar_auditoria(
        sesion,
        usuario_id=cliente.id,
        accion="quitar_domicilio",
        entidad="alquileres" if datos.alquiler_id else "ventas",
        entidad_id=operacion.id,
        antes={"total": anterior},
        despues={"domicilio_id": domicilio.id, "valor_envio": 0, "total": operacion.total},
    )
    sesion.commit()
    return DomicilioConTotales(domicilio, operacion.valor_envio, operacion.total)


# --- Consultas -------------------------------------------------------------------------------


def _consulta_con_totales() -> Select:
    """Domicilios con el envío y el total de su operación (alquiler o venta)."""
    return (
        select(
            Domicilio,
            func.coalesce(Alquiler.valor_envio, Venta.valor_envio),
            func.coalesce(Alquiler.total, Venta.total),
        )
        .outerjoin(Alquiler, Alquiler.id == Domicilio.alquiler_id)
        .outerjoin(Venta, Venta.id == Domicilio.venta_id)
        .options(
            joinedload(Domicilio.zona),
            joinedload(Domicilio.cliente),
            joinedload(Domicilio.domiciliario),
            joinedload(Domicilio.vehiculo_transporte),
        )
        .order_by(Domicilio.id.desc())
    )


def _con_totales(pagina: ResultadoPagina) -> ResultadoPagina:
    elementos = [DomicilioConTotales(d, envio, total) for d, envio, total in pagina.elementos]
    return ResultadoPagina(elementos, pagina.total, pagina.pagina, pagina.tamano)


def listar_domicilios(
    sesion: Session,
    parametros: ParametrosPagina,
    *,
    cliente_id: int | None = None,
    domiciliario_id: int | None = None,
    estado: EstadoDomicilio | None = None,
    solo_en_ruta: bool = False,
) -> ResultadoPagina:
    consulta = _consulta_con_totales()
    if cliente_id is not None:
        consulta = consulta.where(Domicilio.cliente_id == cliente_id)
    if domiciliario_id is not None:
        consulta = consulta.where(Domicilio.domiciliario_id == domiciliario_id)
    if estado is not None:
        consulta = consulta.where(Domicilio.estado == estado)
    if solo_en_ruta:
        consulta = consulta.where(Domicilio.estado.in_(ESTADOS_EN_RUTA))
    return _con_totales(paginar(sesion, consulta, parametros, filas=True))


def obtener_domicilio(sesion: Session, domicilio_id: int, usuario: Usuario) -> DomicilioConTotales:
    """El cliente ve los suyos; el domiciliario, los que tiene asignados; el despacho, todos."""
    fila = sesion.execute(_consulta_con_totales().where(Domicilio.id == domicilio_id)).first()
    if fila is None:
        raise DomicilioNoEncontrado()
    domicilio, envio, total = fila
    visible = (
        usuario.rol in ROLES_DE_DESPACHO
        or (usuario.rol == Rol.CLIENTE and domicilio.cliente_id == usuario.id)
        or (usuario.rol == Rol.DOMICILIARIO and domicilio.domiciliario_id == usuario.id)
    )
    if not visible:
        raise DomicilioNoEncontrado()
    return DomicilioConTotales(domicilio, envio, total)


def _con_entregas_en_ruta() -> Select:
    return select(Domicilio.domiciliario_id).where(
        Domicilio.estado.in_(ESTADOS_EN_RUTA), Domicilio.domiciliario_id.is_not(None)
    )


def listar_domiciliarios_disponibles(
    sesion: Session, parametros: ParametrosPagina
) -> ResultadoPagina:
    """Domiciliarios activos sin ninguna entrega en ruta (decisión 2 del Sprint 3)."""
    consulta = (
        select(Usuario)
        .where(
            Usuario.rol == Rol.DOMICILIARIO,
            Usuario.activo,
            Usuario.id.not_in(_con_entregas_en_ruta()),
        )
        .order_by(Usuario.nombre_completo, Usuario.id)
    )
    return paginar(sesion, consulta, parametros)


# --- Despacho: asignar el domiciliario -------------------------------------------------------


def _esta_pagada(sesion: Session, domicilio: Domicilio) -> bool:
    if domicilio.alquiler_id is not None:
        estado = sesion.scalar(select(Alquiler.estado).where(Alquiler.id == domicilio.alquiler_id))
        return estado == EstadoAlquiler.CONFIRMADO
    estado = sesion.scalar(select(Venta.estado).where(Venta.id == domicilio.venta_id))
    return estado == EstadoVenta.PAGADA


def asignar_domiciliario(
    sesion: Session,
    domicilio_id: int,
    usuario: Usuario,
    domiciliario_id: int,
    vehiculo_transporte_id: int | None = None,
    *,
    hoy: date | None = None,
    momento: datetime | None = None,
) -> DomicilioConTotales:
    """El administrador o el operador asigna la entrega: ``pendiente`` → ``asignado``.

    Solo si la operación ya está pagada y el domiciliario no tiene entregas en ruta. Si se
    indica un vehículo de la flota, debe estar disponible y libre hoy; queda
    ``asignado_a_domicilio`` mientras dure la entrega.
    """
    if usuario.rol not in ROLES_DE_DESPACHO:
        raise PermisoDenegado()
    hoy = hoy or fechas.hoy()
    momento = momento or fechas.ahora()

    # Orden de bloqueo: el vehículo, luego el domiciliario, luego el domicilio.
    vehiculo = bloquear_vehiculo(sesion, vehiculo_transporte_id) if vehiculo_transporte_id else None
    domiciliario = sesion.scalars(
        select(Usuario)
        .where(Usuario.id == domiciliario_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    domicilio = sesion.scalars(
        select(Domicilio)
        .where(Domicilio.id == domicilio_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if domicilio is None:
        raise DomicilioNoEncontrado()
    validar_transicion(domicilio.estado, EstadoDomicilio.ASIGNADO)
    if not _esta_pagada(sesion, domicilio):
        raise DomicilioSinPagar()
    if (
        domiciliario is None
        or domiciliario.rol != Rol.DOMICILIARIO
        or not domiciliario.activo
        or sesion.scalar(
            _con_entregas_en_ruta().where(Domicilio.domiciliario_id == domiciliario.id)
        )
    ):
        raise DomiciliarioNoDisponible()
    if vehiculo is not None:
        _validar_vehiculo_de_transporte(sesion, vehiculo, domicilio, hoy, momento)

    domicilio.domiciliario_id = domiciliario.id
    if vehiculo is not None:
        domicilio.vehiculo_transporte_id = vehiculo.id
        motivo = f"Transporte del domicilio #{domicilio.id}"
        cambiar_estado_vehiculo(
            sesion, vehiculo, EstadoVehiculo.ASIGNADO_A_DOMICILIO, usuario, motivo
        )
    cambiar_estado_domicilio(sesion, domicilio, EstadoDomicilio.ASIGNADO, usuario.id)
    registrar_auditoria(
        sesion,
        usuario_id=usuario.id,
        accion="asignar",
        entidad="domicilios",
        entidad_id=domicilio.id,
        despues={
            "domiciliario_id": domiciliario.id,
            "vehiculo_transporte_id": vehiculo_transporte_id,
        },
    )
    sesion.commit()
    return obtener_domicilio(sesion, domicilio.id, usuario)


def _validar_vehiculo_de_transporte(
    sesion: Session, vehiculo, domicilio: Domicilio, hoy: date, momento: datetime
) -> None:
    if vehiculo.estado != EstadoVehiculo.DISPONIBLE:
        raise VehiculoDeTransporteNoDisponible(
            f"La unidad {vehiculo.codigo} está en '{vehiculo.estado.value}'."
        )
    ocupada_hoy = consulta_vehiculos_ocupados(hoy, hoy, momento).where(
        Alquiler.vehiculo_id == vehiculo.id
    )
    if sesion.scalars(ocupada_hoy).first() is not None:
        raise VehiculoDeTransporteNoDisponible(
            f"La unidad {vehiculo.codigo} tiene un alquiler hoy."
        )
    if domicilio.alquiler_id is not None:
        alquilada = sesion.scalar(
            select(Alquiler.vehiculo_id).where(Alquiler.id == domicilio.alquiler_id)
        )
        if alquilada == vehiculo.id:
            raise VehiculoDeTransporteNoDisponible(
                "Esa es la unidad que se entrega, no puede ser también el transporte."
            )
