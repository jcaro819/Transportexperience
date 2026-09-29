"""Transiciones permitidas entre estados de un vehículo (CLAUDE.md 7.2, SRS 3.3.6).

Es la única fuente de verdad: todo cambio de estado pasa por ``validar_transicion``. Una
transición que no está en la tabla se rechaza en el código, no en la interfaz.

    disponible  → alquilado → disponible              (entrega y devolución de un alquiler)
    disponible  → reservado → vendido (terminal)       (compra pendiente de pago)
                  reservado → disponible               (el pago de la compra no llegó)
    disponible  → asignado_a_domicilio → disponible    (vehículo del domiciliario)
    cualquiera  → mantenimiento → disponible           (salvo vendido; volver requiere operador)
"""

from app.modulos.inventario.excepciones import TransicionInvalida
from app.modulos.inventario.modelos import EstadoVehiculo as E

TRANSICIONES: dict[E, frozenset[E]] = {
    E.DISPONIBLE: frozenset({E.ALQUILADO, E.RESERVADO, E.ASIGNADO_A_DOMICILIO, E.MANTENIMIENTO}),
    E.ALQUILADO: frozenset({E.DISPONIBLE, E.MANTENIMIENTO}),
    E.RESERVADO: frozenset({E.VENDIDO, E.DISPONIBLE, E.MANTENIMIENTO}),
    E.ASIGNADO_A_DOMICILIO: frozenset({E.DISPONIBLE, E.MANTENIMIENTO}),
    E.MANTENIMIENTO: frozenset({E.DISPONIBLE}),
    E.VENDIDO: frozenset(),
}


def es_transicion_valida(actual: E, nuevo: E) -> bool:
    return nuevo in TRANSICIONES[actual]


def validar_transicion(actual: E, nuevo: E) -> None:
    """Lanza ``TransicionInvalida`` si la tabla no permite pasar de ``actual`` a ``nuevo``."""
    if not es_transicion_valida(actual, nuevo):
        raise TransicionInvalida(f"La unidad no puede pasar de '{actual}' a '{nuevo}'.")
