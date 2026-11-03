"""Transiciones permitidas entre estados de un domicilio (CLAUDE.md 7.2, SRS 3.1.7).

    pendiente → asignado → recogido → en_camino → entregado (terminal)
    cualquiera salvo entregado → cancelado (terminal)

HU-06 usa ``pendiente → asignado`` y la cancelación de un pendiente. Los demás cambios los
hace el domiciliario con HU-07.
"""

from app.modulos.domicilios.excepciones import TransicionDeDomicilioInvalida
from app.modulos.domicilios.modelos import EstadoDomicilio as E

TRANSICIONES: dict[E, frozenset[E]] = {
    E.PENDIENTE: frozenset({E.ASIGNADO, E.CANCELADO}),
    E.ASIGNADO: frozenset({E.RECOGIDO, E.CANCELADO}),
    E.RECOGIDO: frozenset({E.EN_CAMINO, E.CANCELADO}),
    E.EN_CAMINO: frozenset({E.ENTREGADO, E.CANCELADO}),
    E.ENTREGADO: frozenset(),
    E.CANCELADO: frozenset(),
}


def es_transicion_valida(actual: E, nuevo: E) -> bool:
    return nuevo in TRANSICIONES[actual]


def validar_transicion(actual: E, nuevo: E) -> None:
    if not es_transicion_valida(actual, nuevo):
        raise TransicionDeDomicilioInvalida(
            f"El domicilio está en '{actual}' y no puede pasar a '{nuevo}'."
        )
