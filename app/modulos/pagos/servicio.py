"""Reglas de negocio de los pagos (HU-05).

Por ahora el cobro de alquileres (HU-03) y ventas (HU-04) con la pasarela que se le pase,
y el registro de devoluciones como pagos de compensación. Los webhooks, Wompi y los
comprobantes PDF llegan con HU-05.
"""

import logging
import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auditoria import registrar_auditoria
from app.modulos.pagos.excepciones import MetodoDePagoNoDisponible
from app.modulos.pagos.modelos import EstadoPago, MetodoPago, Pago, TipoPago
from app.modulos.pagos.pasarela import PasarelaPagos

registro = logging.getLogger(__name__)


def obtener_metodo_activo(sesion: Session, codigo: str) -> MetodoPago:
    """Método de pago habilitado por el administrador (SRS 3.5.3)."""
    metodo = sesion.scalars(
        select(MetodoPago).where(MetodoPago.codigo == codigo, MetodoPago.activo)
    ).one_or_none()
    if metodo is None:
        raise MetodoDePagoNoDisponible()
    return metodo


def cobrar(
    sesion: Session,
    pasarela: PasarelaPagos,
    monto: int,
    metodo: MetodoPago,
    momento: datetime,
    *,
    alquiler_id: int | None = None,
    venta_id: int | None = None,
) -> Pago:
    """Inicia el cobro de un alquiler o una venta y guarda el pago con el resultado.

    No hace commit: el pago se confirma en la misma transacción que actualiza la operación.
    """
    prefijo = "ALQ" if alquiler_id is not None else "VEN"
    referencia = f"{prefijo}-{alquiler_id or venta_id}-{secrets.token_hex(4).upper()}"
    resultado = pasarela.cobrar(referencia, monto, metodo.codigo)
    pago = Pago(
        referencia=referencia,
        tipo=TipoPago.COBRO,
        alquiler_id=alquiler_id,
        venta_id=venta_id,
        metodo_pago_id=metodo.id,
        monto=monto,
        estado=resultado.estado,
        proveedor=pasarela.nombre,
        id_transaccion_pasarela=resultado.id_transaccion,
        aprobado_en=momento if resultado.estado == EstadoPago.APROBADO else None,
        detalle_error=resultado.detalle,
    )
    sesion.add(pago)
    sesion.flush()
    registro.info(
        "Cobro",
        extra={
            "referencia": referencia,
            "alquiler_id": alquiler_id,
            "venta_id": venta_id,
            "estado": pago.estado.value,
        },
    )
    return pago


def registrar_devolucion(
    sesion: Session, cobro: Pago, motivo: str, usuario_id: int | None = None
) -> Pago:
    """Registra la devolución de un cobro aprobado con un pago de compensación (CLAUDE.md 7.3).

    El cobro aprobado no se toca: la compensación es otro registro que lo referencia. Queda
    ``pendiente`` hasta que se ejecute en la pasarela (llega con HU-05). No hace commit.
    """
    devolucion = Pago(
        referencia=f"DEV-{cobro.id}-{secrets.token_hex(4).upper()}",
        tipo=TipoPago.COMPENSACION,
        alquiler_id=cobro.alquiler_id,
        venta_id=cobro.venta_id,
        metodo_pago_id=cobro.metodo_pago_id,
        monto=cobro.monto,
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
        despues={"devolucion_id": devolucion.id, "monto": cobro.monto, "motivo": motivo},
    )
    return devolucion
