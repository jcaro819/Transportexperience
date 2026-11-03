"""Pasarela Wompi en modo **sandbox** (HU-05). Nunca producción, nunca dinero real.

Referencia: https://docs.wompi.co (Ambientes y llaves, Tokens de aceptación, Métodos de
pago, Eventos). Lo que usa este cliente:

- ``GET /merchants/info`` (llave pública): tokens de aceptación de términos y de datos
  personales, obligatorios al crear una transacción. El endpoint viejo
  ``GET /merchants/:llave`` deja de existir el 31/10/2026.
- ``POST /transactions`` (llave pública + firma de integridad): crea el cobro.
- ``GET /transactions/:id``: para obtener la URL del banco en PSE.
- ``GET /transactions?reference=`` (llave privada): consulta de respaldo por referencia.
- ``GET /pse/financial_institutions`` (llave pública): bancos de PSE.

Los tiempos de espera son cortos (SRS: respuesta < 3 s). Si Wompi no responde, el pago
queda ``pendiente`` y lo resuelve el webhook o la consulta de respaldo.
"""

import hashlib
import hmac
import logging
import time
from typing import Any

import httpx

from app.config import Configuracion
from app.modulos.pagos.excepciones import PasarelaNoDisponible
from app.modulos.pagos.modelos import EstadoPago
from app.modulos.pagos.pasarela import (
    BancoPse,
    ConfiguracionPublica,
    ResultadoCobro,
    SolicitudCobro,
)

registro = logging.getLogger(__name__)

# Fija en el código a propósito: este proyecto solo puede hablar con el sandbox.
URL_SANDBOX = "https://sandbox.wompi.co/v1"
MONEDA = "COP"
_TIEMPO_ESPERA = httpx.Timeout(2.5, connect=1.5)
_VIGENCIA_TOKENS_SEGUNDOS = 300

ESTADOS_WOMPI = {
    "APPROVED": EstadoPago.APROBADO,
    "DECLINED": EstadoPago.RECHAZADO,
    "VOIDED": EstadoPago.RECHAZADO,  # anulada: para nosotros, no se cobró
    "ERROR": EstadoPago.ERROR,
    "PENDING": EstadoPago.PENDIENTE,
}

# Tokens de aceptación por llave pública, con la hora en que se pidieron.
_cache_comercio: dict[str, tuple[float, dict[str, Any]]] = {}


# --- Firmas (funciones puras, con tests) ------------------------------------------------------


def firma_integridad(referencia: str, monto_en_centavos: int, secreto: str) -> str:
    """SHA-256 de ``referencia + monto_en_centavos + moneda + secreto``, en hex."""
    texto = f"{referencia}{monto_en_centavos}{MONEDA}{secreto}"
    return hashlib.sha256(texto.encode()).hexdigest()


def _valor_en_ruta(datos: dict[str, Any], ruta: str) -> Any:
    valor: Any = datos
    for parte in ruta.split("."):
        valor = valor[parte]
    return valor


def verificar_firma_evento(evento: dict[str, Any], secreto: str) -> bool:
    """Verifica el ``checksum`` de un evento (webhook) de Wompi.

    SHA-256 de los valores de ``signature.properties`` (rutas dentro de ``data``, en su
    orden) + ``timestamp`` + secreto de eventos. Comparación en tiempo constante.
    """
    try:
        firma = evento["signature"]
        valores = "".join(str(_valor_en_ruta(evento["data"], p)) for p in firma["properties"])
        texto = f"{valores}{evento['timestamp']}{secreto}"
        esperado = hashlib.sha256(texto.encode()).hexdigest()
        return hmac.compare_digest(esperado.lower(), str(firma["checksum"]).lower())
    except (KeyError, TypeError, AttributeError):
        return False


def monto_en_centavos(pesos: int) -> int:
    return pesos * 100


def resultado_de_transaccion(transaccion: dict[str, Any]) -> ResultadoCobro:
    """Traduce una transacción de Wompi a nuestro ``ResultadoCobro``."""
    estado = ESTADOS_WOMPI.get(transaccion.get("status", ""), EstadoPago.PENDIENTE)
    extra = (transaccion.get("payment_method") or {}).get("extra") or {}
    return ResultadoCobro(
        estado=estado,
        id_transaccion=transaccion.get("id"),
        detalle=transaccion.get("status_message"),
        url_redireccion=extra.get("async_payment_url"),
    )


# --- Cliente ---------------------------------------------------------------------------------


class PasarelaWompi:
    nombre = "wompi"

    def __init__(self, configuracion: Configuracion, cliente: httpx.Client | None = None) -> None:
        self._llave_publica = configuracion.wompi_llave_publica
        self._llave_privada = configuracion.wompi_llave_privada
        self._secreto_integridad = configuracion.wompi_secreto_integridad
        # ``cliente`` permite inyectar un transporte simulado en los tests.
        self._http = cliente or httpx.Client(base_url=URL_SANDBOX, timeout=_TIEMPO_ESPERA)

    def _pedir(self, metodo: str, ruta: str, *, privada: bool = False, **kwargs) -> dict:
        llave = self._llave_privada if privada else self._llave_publica
        encabezados = {"Authorization": f"Bearer {llave}", **kwargs.pop("headers", {})}
        try:
            respuesta = self._http.request(metodo, ruta, headers=encabezados, **kwargs)
        except httpx.HTTPError as error:
            registro.warning("Wompi no respondió", extra={"ruta": ruta, "error": str(error)})
            raise PasarelaNoDisponible() from error
        if respuesta.status_code >= 500:
            registro.warning("Wompi falló", extra={"ruta": ruta, "http": respuesta.status_code})
            raise PasarelaNoDisponible()
        cuerpo = respuesta.json() if respuesta.content else {}
        if respuesta.status_code >= 400:
            raise _ErrorDeWompi(cuerpo)
        return cuerpo

    def _datos_comercio(self) -> dict[str, Any]:
        guardado = _cache_comercio.get(self._llave_publica)
        if guardado and time.monotonic() - guardado[0] < _VIGENCIA_TOKENS_SEGUNDOS:
            return guardado[1]
        datos = self._pedir(
            "GET", "/merchants/info", headers={"x-merchant-public-key": self._llave_publica}
        )["data"]
        _cache_comercio[self._llave_publica] = (time.monotonic(), datos)
        return datos

    def cobrar(self, solicitud: SolicitudCobro) -> ResultadoCobro:
        comercio = self._datos_comercio()
        centavos = monto_en_centavos(solicitud.monto)
        cuerpo = {
            "amount_in_cents": centavos,
            "currency": MONEDA,
            "customer_email": solicitud.correo,
            "reference": solicitud.referencia,
            "signature": firma_integridad(solicitud.referencia, centavos, self._secreto_integridad),
            "acceptance_token": comercio["presigned_acceptance"]["acceptance_token"],
            "accept_personal_auth": comercio["presigned_personal_data_auth"]["acceptance_token"],
            "payment_method": _metodo_de_pago(solicitud),
        }
        try:
            transaccion = self._pedir("POST", "/transactions", json=cuerpo)["data"]
        except _ErrorDeWompi as error:
            # Wompi rechazó la solicitud (datos inválidos): no se creó ningún cobro.
            return ResultadoCobro(EstadoPago.ERROR, detalle=error.mensaje)
        resultado = resultado_de_transaccion(transaccion)
        if solicitud.metodo == "pse" and resultado.url_redireccion is None:
            # La URL del banco aparece unos instantes después; se intenta una vez más.
            try:
                transaccion = self._pedir("GET", f"/transactions/{resultado.id_transaccion}")
                resultado = resultado_de_transaccion(transaccion["data"])
            except (PasarelaNoDisponible, _ErrorDeWompi):
                pass  # el cliente la verá al consultar el pago
        return resultado

    def consultar(self, referencia: str) -> ResultadoCobro | None:
        try:
            datos = self._pedir(
                "GET", "/transactions", privada=True, params={"reference": referencia}
            )["data"]
        except _ErrorDeWompi:
            return None
        if not datos:
            return None
        return resultado_de_transaccion(datos[-1])

    def bancos_pse(self) -> list[BancoPse]:
        try:
            datos = self._pedir("GET", "/pse/financial_institutions")["data"]
        except _ErrorDeWompi as error:
            raise PasarelaNoDisponible() from error
        return [
            BancoPse(b["financial_institution_code"], b["financial_institution_name"])
            for b in datos
        ]

    def configuracion_publica(self) -> ConfiguracionPublica:
        try:
            comercio = self._datos_comercio()
        except _ErrorDeWompi as error:
            raise PasarelaNoDisponible() from error
        return ConfiguracionPublica(
            proveedor=self.nombre,
            llave_publica=self._llave_publica,
            url_api=URL_SANDBOX,
            terminos_url=comercio["presigned_acceptance"]["permalink"],
            datos_personales_url=comercio["presigned_personal_data_auth"]["permalink"],
        )


class _ErrorDeWompi(Exception):
    """Wompi respondió 4xx: la solicitud no es válida."""

    def __init__(self, cuerpo: dict[str, Any]) -> None:
        error = cuerpo.get("error") or {}
        self.mensaje = str(error.get("messages") or error.get("reason") or cuerpo)[:500]
        super().__init__(self.mensaje)


def _metodo_de_pago(solicitud: SolicitudCobro) -> dict[str, Any]:
    if solicitud.metodo == "tarjeta" and solicitud.tarjeta:
        return {
            "type": "CARD",
            "token": solicitud.tarjeta.token,
            "installments": solicitud.tarjeta.cuotas,
        }
    if solicitud.metodo == "pse" and solicitud.pse:
        return {
            "type": "PSE",
            "user_type": 0 if solicitud.pse.tipo_persona == "natural" else 1,
            "user_legal_id_type": solicitud.pse.tipo_documento,
            "user_legal_id": solicitud.pse.documento,
            "financial_institution_code": solicitud.pse.banco,
            "payment_description": solicitud.descripcion[:64],
        }
    raise ValueError(f"Faltan los datos del método '{solicitud.metodo}'.")
