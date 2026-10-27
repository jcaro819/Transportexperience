"""Cambios de estado de un domicilio y su cancelación cuando cae su operación (HU-06).

Lo usan los alquileres y las ventas: si una reserva o compra expira o se cancela, su
domicilio pendiente se cancela con ella (si no, quedaría vivo y bloquearía un domicilio
nuevo para la misma operación). Vive aparte del servicio para no crear imports circulares.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modulos.domicilios.estados import validar_transicion
from app.modulos.domicilios.modelos import Domicilio, EstadoDomicilio, HistorialEstadoDomicilio


def cambiar_estado_domicilio(
    sesion: Session,
    domicilio: Domicilio,
    nuevo: EstadoDomicilio,
    usuario_id: int | None,
) -> None:
    """Único camino para cambiar el estado de un domicilio: valida y deja el historial.

    El historial (quién y cuándo) es lo que muestra el rastreo de HU-07. No hace commit.
    """
    anterior = domicilio.estado
    validar_transicion(anterior, nuevo)
    domicilio.estado = nuevo
    sesion.add(
        HistorialEstadoDomicilio(
            domicilio_id=domicilio.id,
            estado_anterior=anterior,
            estado_nuevo=nuevo,
            cambiado_por_id=usuario_id,
        )
    )


def domicilio_vigente(
    sesion: Session, *, alquiler_id: int | None = None, venta_id: int | None = None
) -> Domicilio | None:
    """El domicilio no cancelado de la operación, bloqueado con ``FOR UPDATE``."""
    operacion = (
        Domicilio.alquiler_id == alquiler_id if alquiler_id else Domicilio.venta_id == venta_id
    )
    return sesion.scalars(
        select(Domicilio)
        .where(operacion, Domicilio.estado != EstadoDomicilio.CANCELADO)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()


def cancelar_domicilio_pendiente(
    sesion: Session,
    motivo: str,
    usuario_id: int | None = None,
    *,
    alquiler_id: int | None = None,
    venta_id: int | None = None,
) -> None:
    """Si la operación tiene un domicilio aún sin asignar, lo cancela. No hace commit.

    Debe llamarse con la operación ya bloqueada (orden global: operación, luego domicilio).
    """
    domicilio = domicilio_vigente(sesion, alquiler_id=alquiler_id, venta_id=venta_id)
    if domicilio is not None and domicilio.estado == EstadoDomicilio.PENDIENTE:
        domicilio.motivo_cancelacion = motivo
        cambiar_estado_domicilio(sesion, domicilio, EstadoDomicilio.CANCELADO, usuario_id)
