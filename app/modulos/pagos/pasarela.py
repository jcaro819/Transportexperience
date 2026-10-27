"""Interfaz con la pasarela de pagos y sus implementaciones (CLAUDE.md sección 8).

El resto del sistema solo conoce ``PasarelaPagos``. Hay dos implementaciones:

- ``PasarelaFalsa``: no toca la red ni mueve dinero. Para tests y desarrollo.
- ``PasarelaWompi`` (``wompi.py``): Wompi en **sandbox**. Se escoge con
  ``PAGOS_PROVEEDOR=wompi`` y las cuatro llaves de prueba en el ``.env``.

Con Wompi el cobro suele quedar ``pendiente`` y la verdad llega después por el webhook o
por la consulta de respaldo (``consultar``). Por eso quien llama trata los cuatro
resultados: aprobado, rechazado, error y pendiente.
"""

from dataclasses import dataclass
from typing import Literal, Protocol

from app.config import obtener_configuracion
from app.modulos.pagos.modelos import EstadoPago


@dataclass(frozen=True)
class DatosTarjeta:
    # El token lo genera el frontend con la llave pública: el número de la tarjeta nunca
    # pasa por este backend (tokenización, HU-05).
    token: str
    cuotas: int = 1


@dataclass(frozen=True)
class DatosPse:
    tipo_persona: Literal["natural", "juridica"]
    tipo_documento: Literal["CC", "NIT"]
    documento: str
    banco: str  # código del banco, de bancos_pse()


@dataclass(frozen=True)
class SolicitudCobro:
    referencia: str
    monto: int  # pesos enteros
    metodo: str  # "tarjeta" o "pse"
    correo: str
    descripcion: str
    tarjeta: DatosTarjeta | None = None
    pse: DatosPse | None = None


@dataclass(frozen=True)
class ResultadoCobro:
    estado: EstadoPago
    id_transaccion: str | None = None
    detalle: str | None = None
    url_redireccion: str | None = None  # PSE: la página del banco


@dataclass(frozen=True)
class BancoPse:
    codigo: str
    nombre: str


@dataclass(frozen=True)
class ConfiguracionPublica:
    """Lo que el frontend necesita para tokenizar la tarjeta y mostrar los términos."""

    proveedor: str
    llave_publica: str | None
    url_api: str | None
    terminos_url: str | None
    datos_personales_url: str | None


class PasarelaPagos(Protocol):
    nombre: str

    def cobrar(self, solicitud: SolicitudCobro) -> ResultadoCobro:
        """Inicia el cobro. Lanza ``PasarelaNoDisponible`` si no se sabe si se creó."""
        ...

    def consultar(self, referencia: str) -> ResultadoCobro | None:
        """Consulta de respaldo: el estado actual de la transacción con esa referencia."""
        ...

    def bancos_pse(self) -> list[BancoPse]: ...

    def configuracion_publica(self) -> ConfiguracionPublica: ...


class PasarelaFalsa:
    """Pasarela de mentiras para desarrollo y tests: no toca la red ni mueve dinero.

    ``resultado`` es lo que responde al cobrar (aprobado, por defecto). ``consulta`` es lo
    que responde la consulta de respaldo (``None``: la pasarela no conoce la referencia).
    """

    nombre = "falso"

    def __init__(
        self,
        resultado: EstadoPago = EstadoPago.APROBADO,
        *,
        consulta: EstadoPago | None = None,
    ) -> None:
        self.resultado = resultado
        self.consulta = consulta
        self.solicitudes: list[SolicitudCobro] = []

    def cobrar(self, solicitud: SolicitudCobro) -> ResultadoCobro:
        self.solicitudes.append(solicitud)
        detalle = (
            None if self.resultado == EstadoPago.APROBADO else "Simulado por la pasarela falsa."
        )
        url = "https://pse.falso.test/banco" if solicitud.metodo == "pse" else None
        return ResultadoCobro(
            self.resultado, f"falso-{solicitud.referencia}", detalle, url_redireccion=url
        )

    def consultar(self, referencia: str) -> ResultadoCobro | None:
        if self.consulta is None:
            return None
        return ResultadoCobro(self.consulta, f"falso-{referencia}")

    def bancos_pse(self) -> list[BancoPse]:
        return [
            BancoPse("1", "Banco que aprueba (prueba)"),
            BancoPse("2", "Banco que rechaza (prueba)"),
        ]

    def configuracion_publica(self) -> ConfiguracionPublica:
        return ConfiguracionPublica("falso", None, None, None, None)


def obtener_pasarela() -> PasarelaPagos:
    """Dependencia de FastAPI: la pasarela configurada en ``PAGOS_PROVEEDOR``."""
    configuracion = obtener_configuracion()
    if configuracion.pagos_proveedor == "falso":
        return PasarelaFalsa()
    from app.modulos.pagos.wompi import PasarelaWompi  # solo se carga si se usa

    return PasarelaWompi(configuracion)
