"""Transiciones permitidas entre estados de un alquiler (CLAUDE.md 7.2, SRS 3.3.6).

Es la única fuente de verdad: todo cambio de estado de un alquiler pasa por
``validar_transicion``. Lo que no está en la tabla se rechaza en el código.

    pendiente_pago → confirmado    (el pago se aprobó)
    pendiente_pago → cancelado     (el cliente desiste antes de pagar)
    pendiente_pago → expirado      (no pagó dentro de los 15 minutos del bloqueo)
    confirmado     → en_curso      (el operador entrega el vehículo)
    en_curso       → finalizado    (el operador recibe el vehículo)

Un alquiler ya pagado (``confirmado``) no lo cancela el cliente: esa cancelación exige
devolver el dinero con un pago de compensación, y llega con HU-05.
"""

from app.modulos.alquileres.excepciones import TransicionDeAlquilerInvalida
from app.modulos.alquileres.modelos import EstadoAlquiler as E

TRANSICIONES: dict[E, frozenset[E]] = {
    E.PENDIENTE_PAGO: frozenset({E.CONFIRMADO, E.CANCELADO, E.EXPIRADO}),
    E.CONFIRMADO: frozenset({E.EN_CURSO}),
    E.EN_CURSO: frozenset({E.FINALIZADO}),
    E.FINALIZADO: frozenset(),
    E.CANCELADO: frozenset(),
    E.EXPIRADO: frozenset(),
}


def es_transicion_valida(actual: E, nuevo: E) -> bool:
    return nuevo in TRANSICIONES[actual]


def validar_transicion(actual: E, nuevo: E) -> None:
    """Lanza ``TransicionDeAlquilerInvalida`` si la tabla no permite el cambio."""
    if not es_transicion_valida(actual, nuevo):
        raise TransicionDeAlquilerInvalida(
            f"El alquiler está en '{actual}' y no puede pasar a '{nuevo}'."
        )
