"""Consultas de solo lectura sobre las ventas (HU-04) que usan otros módulos.

Viven aparte del servicio para que inventario pueda importarlas sin crear un import
circular, igual que ``alquileres/consultas.py``.
"""

from datetime import datetime

from sqlalchemy import Select, select

from app.modulos.ventas.modelos import EstadoVenta, ItemVenta, Venta


def consulta_compra_pendiente_de_vehiculo(vehiculo_id: int, momento: datetime) -> Select:
    """Ventas sin pagar, con el bloqueo aún vigente, que apartan esta unidad.

    Una venta pendiente cuyo ``expira_en`` ya pasó no cuenta: está a punto de expirar.
    """
    return (
        select(Venta.id)
        .join(Venta.items)
        .where(
            ItemVenta.vehiculo_id == vehiculo_id,
            Venta.estado == EstadoVenta.PENDIENTE_PAGO,
            Venta.expira_en > momento,
        )
    )
