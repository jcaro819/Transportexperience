"""Reglas de negocio de los pagos (HU-05).

Por ahora solo el cobro que usa el alquiler (HU-03) con la pasarela que se le pase. Los
webhooks, Wompi y los comprobantes PDF llegan con HU-05.
"""

import logging
import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

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


def cobrar_alquiler(
    sesion: Session,
    pasarela: PasarelaPagos,
    alquiler_id: int,
    monto: int,
    metodo: MetodoPago,
    momento: datetime,
) -> Pago:
    """Inicia el cobro de un alquiler y guarda el pago con el resultado de la pasarela.

    No hace commit: el pago se confirma en la misma transacción que actualiza el alquiler.
    """
    referencia = f"ALQ-{alquiler_id}-{secrets.token_hex(4).upper()}"
    resultado = pasarela.cobrar(referencia, monto, metodo.codigo)
    pago = Pago(
        referencia=referencia,
        tipo=TipoPago.COBRO,
        alquiler_id=alquiler_id,
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
        "Cobro de alquiler",
        extra={"referencia": referencia, "alquiler_id": alquiler_id, "estado": pago.estado.value},
    )
    return pago
