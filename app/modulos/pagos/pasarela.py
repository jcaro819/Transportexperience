"""Interfaz con la pasarela de pagos y sus implementaciones (CLAUDE.md sección 8).

El resto del sistema solo conoce ``PasarelaPagos``. Hoy existe la implementación falsa,
que no toca la red y responde al instante; la de Wompi sandbox llega con HU-05 y se escoge
con ``PAGOS_PROVEEDOR=wompi`` en el ``.env``.

Con Wompi el cobro casi siempre queda ``pendiente`` y la verdad llega después por el
webhook (CLAUDE.md 7.3). Por eso quien llama debe tratar los tres resultados: aprobado,
rechazado y pendiente.
"""

from dataclasses import dataclass
from typing import Protocol

from app.config import obtener_configuracion
from app.modulos.pagos.excepciones import PasarelaNoDisponible
from app.modulos.pagos.modelos import EstadoPago


@dataclass(frozen=True)
class ResultadoCobro:
    estado: EstadoPago
    id_transaccion: str | None = None
    detalle: str | None = None


class PasarelaPagos(Protocol):
    """Lo que el sistema necesita de una pasarela: iniciar un cobro."""

    nombre: str

    def cobrar(self, referencia: str, monto: int, metodo: str) -> ResultadoCobro:
        """Inicia el cobro de ``monto`` pesos con el método ``metodo`` (``tarjeta``, ``pse``)."""
        ...


class PasarelaFalsa:
    """Pasarela de mentiras para desarrollo y tests: no toca la red ni mueve dinero.

    Aprueba todo, salvo que se cree con ``aprueba=False`` (para probar un rechazo).
    """

    nombre = "falso"

    def __init__(self, *, aprueba: bool = True) -> None:
        self.aprueba = aprueba

    def cobrar(self, referencia: str, monto: int, metodo: str) -> ResultadoCobro:
        if self.aprueba:
            return ResultadoCobro(EstadoPago.APROBADO, id_transaccion=f"falso-{referencia}")
        return ResultadoCobro(
            EstadoPago.RECHAZADO,
            id_transaccion=f"falso-{referencia}",
            detalle="Rechazo simulado por la pasarela falsa.",
        )


def obtener_pasarela() -> PasarelaPagos:
    """Dependencia de FastAPI: la pasarela configurada en ``PAGOS_PROVEEDOR``."""
    if obtener_configuracion().pagos_proveedor == "falso":
        return PasarelaFalsa()
    # PAGOS_PROVEEDOR=wompi: la implementación llega con HU-05.
    raise PasarelaNoDisponible()
