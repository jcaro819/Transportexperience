"""Transiciones permitidas entre estados de una venta (CLAUDE.md 7.2, SRS 3.3.6).

    pendiente_pago → pagada      (el pago se aprobó y todas las unidades seguían apartadas)
    pendiente_pago → cancelada   (el cliente desiste, o se devolvió el dinero: decisión 2)
    pendiente_pago → expirada    (no se pagó dentro de los 15 minutos del bloqueo)

``pagada`` es terminal: un vehículo vendido no vuelve a la flota.
"""

from app.modulos.ventas.excepciones import TransicionDeVentaInvalida
from app.modulos.ventas.modelos import EstadoVenta as E

TRANSICIONES: dict[E, frozenset[E]] = {
    E.PENDIENTE_PAGO: frozenset({E.PAGADA, E.CANCELADA, E.EXPIRADA}),
    E.PAGADA: frozenset(),
    E.CANCELADA: frozenset(),
    E.EXPIRADA: frozenset(),
}


def es_transicion_valida(actual: E, nuevo: E) -> bool:
    return nuevo in TRANSICIONES[actual]


def validar_transicion(actual: E, nuevo: E) -> None:
    """Lanza ``TransicionDeVentaInvalida`` si la tabla no permite el cambio."""
    if not es_transicion_valida(actual, nuevo):
        raise TransicionDeVentaInvalida(
            f"La compra está en '{actual}' y no puede pasar a '{nuevo}'."
        )
