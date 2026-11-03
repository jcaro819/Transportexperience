"""Reglas de negocio de los pagos (HU-05, CLAUDE.md 7.3).

Piezas de bajo nivel que usan los alquileres y las ventas. La orquestación del cobro (las
dos fases, el webhook y la consulta de respaldo) está en ``procesamiento.py``.

- Un cobro se **guarda como pendiente y se confirma en la base antes** de llamar a la
  pasarela (decisión 2 de HU-05): nunca queda un cobro en la pasarela sin registro aquí.
- Un pago que ya salió de ``pendiente`` no se modifica: los avisos repetidos se ignoran
  (idempotencia) y un aprobado solo se compensa con otro registro.
"""

import logging
import secrets
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auditoria import registrar_auditoria
from app.modulos.pagos.excepciones import MetodoDePagoNoDisponible
from app.modulos.pagos.modelos import EstadoPago, MetodoPago, Pago, TipoPago
from app.modulos.pagos.pasarela import ResultadoCobro

registro = logging.getLogger(__name__)


def obtener_metodo_activo(sesion: Session, codigo: str) -> MetodoPago:
    """Método de pago habilitado por el administrador (SRS 3.5.3)."""
    metodo = sesion.scalars(
        select(MetodoPago).where(MetodoPago.codigo == codigo, MetodoPago.activo)
    ).one_or_none()
    if metodo is None:
        raise MetodoDePagoNoDisponible()
    return metodo


def hay_cobro_pendiente(
    sesion: Session, *, alquiler_id: int | None = None, venta_id: int | None = None
) -> bool:
    """Si la operación tiene un cobro esperando respuesta de la pasarela."""
    operacion = Pago.alquiler_id == alquiler_id if alquiler_id else Pago.venta_id == venta_id
    return bool(
        sesion.scalar(
            select(func.count()).where(
                operacion, Pago.tipo == TipoPago.COBRO, Pago.estado == EstadoPago.PENDIENTE
            )
        )
    )


def crear_cobro_pendiente(
    sesion: Session,
    monto: int,
    metodo: MetodoPago,
    proveedor: str,
    bloqueo_original_hasta: datetime | None,
    *,
    alquiler_id: int | None = None,
    venta_id: int | None = None,
) -> Pago:
    """Registra un cobro en ``pendiente``, antes de llamar a la pasarela. No hace commit."""
    prefijo = "ALQ" if alquiler_id is not None else "VEN"
    pago = Pago(
        referencia=f"{prefijo}-{alquiler_id or venta_id}-{secrets.token_hex(4).upper()}",
        tipo=TipoPago.COBRO,
        alquiler_id=alquiler_id,
        venta_id=venta_id,
        metodo_pago_id=metodo.id,
        monto=monto,
        estado=EstadoPago.PENDIENTE,
        proveedor=proveedor,
        bloqueo_original_hasta=bloqueo_original_hasta,
    )
    sesion.add(pago)
    sesion.flush()
    return pago


def bloquear_pago(sesion: Session, pago_id: int) -> Pago:
    """``FOR UPDATE`` sobre el pago. Va después de bloquear su operación (orden global)."""
    return sesion.scalars(
        select(Pago)
        .where(Pago.id == pago_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()


def registrar_resultado(pago: Pago, resultado: ResultadoCobro, momento: datetime) -> bool:
    """Aplica al pago lo que reporta la pasarela. Devuelve ``True`` si salió de ``pendiente``.

    Idempotente: si el pago ya estaba resuelto, no cambia nada (un webhook repetido, o el
    webhook y la consulta de respaldo diciendo lo mismo). La fila debe estar bloqueada.
    """
    if pago.estado != EstadoPago.PENDIENTE:
        if resultado.estado != pago.estado:
            registro.warning(
                "La pasarela reporta otro estado para un pago ya resuelto; se ignora",
                extra={
                    "referencia": pago.referencia,
                    "guardado": pago.estado.value,
                    "reportado": resultado.estado.value,
                },
            )
        return False
    pago.id_transaccion_pasarela = resultado.id_transaccion or pago.id_transaccion_pasarela
    pago.url_redireccion = resultado.url_redireccion or pago.url_redireccion
    if resultado.estado == EstadoPago.PENDIENTE:
        return False
    pago.estado = resultado.estado
    if resultado.estado == EstadoPago.APROBADO:
        pago.aprobado_en = momento
    else:
        pago.detalle_error = resultado.detalle
    registro.info(
        "Pago resuelto", extra={"referencia": pago.referencia, "estado": pago.estado.value}
    )
    return True


def ya_devuelto(sesion: Session, cobro: Pago) -> int:
    """Suma de las devoluciones ya registradas (pendientes o hechas) de un cobro."""
    # SUM de Postgres devuelve numeric (Decimal en Python); el dinero va siempre en int.
    suma = sesion.scalar(
        select(func.coalesce(func.sum(Pago.monto), 0)).where(
            Pago.pago_compensado_id == cobro.id, Pago.tipo == TipoPago.COMPENSACION
        )
    )
    return int(suma or 0)


def registrar_devolucion(
    sesion: Session,
    cobro: Pago,
    motivo: str,
    usuario_id: int | None = None,
    *,
    monto: int | None = None,
) -> Pago | None:
    """Registra la devolución de un cobro aprobado con un pago de compensación (CLAUDE.md 7.3).

    El cobro aprobado no se toca: la compensación es otro registro que lo referencia. Queda
    ``pendiente`` hasta que el administrador la ejecute en Wompi y la marque. No hace commit.

    Sin ``monto`` se devuelve lo que falte del cobro; con ``monto`` (p. ej., solo el envío,
    HU-07) se devuelve eso. **Nunca se devuelve más de lo cobrado**: se descuentan las
    devoluciones anteriores. Si no queda nada por devolver, no registra nada y devuelve
    ``None``.
    """
    por_devolver = cobro.monto - ya_devuelto(sesion, cobro)
    monto = por_devolver if monto is None else min(monto, por_devolver)
    if monto <= 0:
        return None
    devolucion = Pago(
        referencia=f"DEV-{cobro.id}-{secrets.token_hex(4).upper()}",
        tipo=TipoPago.COMPENSACION,
        alquiler_id=cobro.alquiler_id,
        venta_id=cobro.venta_id,
        metodo_pago_id=cobro.metodo_pago_id,
        monto=monto,
        estado=EstadoPago.PENDIENTE,
        proveedor=cobro.proveedor,
        pago_compensado_id=cobro.id,
        detalle_error=motivo,
    )
    sesion.add(devolucion)
    sesion.flush()
    registrar_auditoria(
        sesion,
        usuario_id=usuario_id,
        accion="compensar",
        entidad="pagos",
        entidad_id=cobro.id,
        despues={"devolucion_id": devolucion.id, "monto": monto, "motivo": motivo},
    )
    registro.warning(
        "Devolución pendiente: el administrador debe atenderla",
        extra={"cobro": cobro.referencia, "devolucion": devolucion.referencia},
    )
    return devolucion


def cobro_aprobado(
    sesion: Session, *, alquiler_id: int | None = None, venta_id: int | None = None
) -> Pago | None:
    """El cobro aprobado de la operación, si existe (hay a lo sumo uno)."""
    operacion = Pago.alquiler_id == alquiler_id if alquiler_id else Pago.venta_id == venta_id
    return sesion.scalars(
        select(Pago).where(
            operacion, Pago.tipo == TipoPago.COBRO, Pago.estado == EstadoPago.APROBADO
        )
    ).one_or_none()
