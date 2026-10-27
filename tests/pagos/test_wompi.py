"""Cliente de Wompi sandbox, sin red: firmas y llamadas con un transporte simulado.

Las firmas se comprueban contra los ejemplos de la documentación oficial
(docs.wompi.co: "Widget & Checkout Web" y "Eventos"). Son valores de ejemplo publicados,
no llaves de ninguna cuenta.
"""

import hashlib
import json

import httpx
import pytest
from pydantic import ValidationError

from app.config import Configuracion
from app.modulos.pagos.excepciones import PasarelaNoDisponible
from app.modulos.pagos.modelos import EstadoPago
from app.modulos.pagos.pasarela import DatosPse, DatosTarjeta, SolicitudCobro
from app.modulos.pagos.wompi import (
    URL_SANDBOX,
    PasarelaWompi,
    _cache_comercio,
    firma_integridad,
    verificar_firma_evento,
)

# --- Firmas -------------------------------------------------------------------------------


def test_firma_de_integridad_coincide_con_el_ejemplo_de_wompi() -> None:
    firma = firma_integridad(
        "sk8-438k4-xmxm392-sn2m2", 490000, "prod_integrity_Z5mMke9x0k8gpErbDqwrJXMqsI6SFli6"
    )
    assert firma == "37c8407747e595535433ef8f6a811d853cd943046624a0ec04662b17bbf33bf5"


SECRETO_EJEMPLO = "prod_events_OcHnIzeBl5socpwByQ4hA52Em3USQ93Z"
# Cadena del paso 3 del ejemplo de la documentación ("Eventos"): valores de las
# propiedades + timestamp + secreto. Ojo: el checksum que publica esa página
# (3476DDA5...) no es el SHA-256 de su propia cadena; el correcto es este (verificado con
# hashlib, 27/10/2026). Se confirma con un evento real del sandbox al tener las llaves.
CADENA_DOCUMENTADA = (
    "1234-1610641025-49201APPROVED44900001530291411prod_events_OcHnIzeBl5socpwByQ4hA52Em3USQ93Z"
)
CHECKSUM_DE_LA_CADENA = "5A18EC5E8FDB7DF463E9F94774CBA8F583BA21BD04A09CEFF2EA68A4BC0AEFBE"


def _evento_del_ejemplo(**cambios) -> dict:
    evento = {
        "event": "transaction.updated",
        "data": {
            "transaction": {
                "id": "1234-1610641025-49201",
                "status": "APPROVED",
                "amount_in_cents": 4490000,
            }
        },
        "signature": {
            "properties": [
                "transaction.id",
                "transaction.status",
                "transaction.amount_in_cents",
            ],
            "checksum": CHECKSUM_DE_LA_CADENA,
        },
        "timestamp": 1530291411,
    }
    evento.update(cambios)
    return evento


def test_la_cadena_firmada_sigue_la_receta_documentada() -> None:
    assert hashlib.sha256(CADENA_DOCUMENTADA.encode()).hexdigest().upper() == CHECKSUM_DE_LA_CADENA


def test_firma_de_evento_valida_con_el_ejemplo_de_wompi() -> None:
    assert verificar_firma_evento(_evento_del_ejemplo(), SECRETO_EJEMPLO)


def test_el_checksum_se_compara_sin_importar_mayusculas() -> None:
    evento = _evento_del_ejemplo()
    evento["signature"]["checksum"] = CHECKSUM_DE_LA_CADENA.lower()
    assert verificar_firma_evento(evento, SECRETO_EJEMPLO)


def test_firma_de_evento_alterado_no_es_valida() -> None:
    evento = _evento_del_ejemplo()
    evento["data"]["transaction"]["status"] = "DECLINED"  # alguien cambió el estado
    assert not verificar_firma_evento(evento, SECRETO_EJEMPLO)


def test_firma_con_otro_secreto_no_es_valida() -> None:
    assert not verificar_firma_evento(_evento_del_ejemplo(), "test_events_otro")


def test_evento_sin_firma_no_es_valido() -> None:
    evento = _evento_del_ejemplo()
    del evento["signature"]
    assert not verificar_firma_evento(evento, SECRETO_EJEMPLO)


# --- Configuración: solo sandbox -----------------------------------------------------------

_LLAVES = {
    "wompi_llave_publica": "pub_test_abc123",
    "wompi_llave_privada": "prv_test_abc123",
    "wompi_secreto_eventos": "test_events_abc123",
    "wompi_secreto_integridad": "test_integrity_abc123",
}


def _configuracion(**cambios) -> Configuracion:
    return Configuracion(
        _env_file=None,
        database_url="postgresql+psycopg://x:y@localhost/z",
        jwt_secreto="s" * 40,
        pagos_proveedor="wompi",
        **(_LLAVES | cambios),
    )


def test_acepta_las_cuatro_llaves_de_sandbox() -> None:
    assert _configuracion().pagos_proveedor == "wompi"


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("wompi_llave_publica", "pub_prod_abc123"),
        ("wompi_llave_privada", "prv_prod_abc123"),
        ("wompi_secreto_eventos", "prod_events_abc123"),
        ("wompi_secreto_integridad", "prod_integrity_abc123"),
    ],
)
def test_rechaza_llaves_de_produccion(campo: str, valor: str) -> None:
    with pytest.raises(ValidationError, match="sandbox"):
        _configuracion(**{campo: valor})


def test_rechaza_las_llaves_de_ejemplo_del_env_example() -> None:
    with pytest.raises(ValidationError, match="WOMPI_LLAVE_PUBLICA"):
        _configuracion(wompi_llave_publica="pub_test_xxxxxxxx")


# --- Llamadas a la API (transporte simulado) -----------------------------------------------

COMERCIO = {
    "data": {
        "presigned_acceptance": {"acceptance_token": "tok-terminos", "permalink": "https://t"},
        "presigned_personal_data_auth": {
            "acceptance_token": "tok-datos",
            "permalink": "https://d",
        },
    }
}


class Wompi:
    """Simula la API de Wompi y guarda cada solicitud que recibe."""

    def __init__(self, respuestas: dict[tuple[str, str], object]) -> None:
        self.respuestas = respuestas
        self.solicitudes: list[httpx.Request] = []

    def __call__(self, solicitud: httpx.Request) -> httpx.Response:
        self.solicitudes.append(solicitud)
        respuesta = self.respuestas[(solicitud.method, solicitud.url.path)]
        if isinstance(respuesta, Exception):
            raise respuesta
        if isinstance(respuesta, list):  # respuestas sucesivas
            respuesta = respuesta.pop(0)
        estado, cuerpo = respuesta
        return httpx.Response(estado, json=cuerpo)


@pytest.fixture(autouse=True)
def _sin_cache() -> None:
    _cache_comercio.clear()


def _pasarela(wompi: Wompi) -> PasarelaWompi:
    cliente = httpx.Client(base_url=URL_SANDBOX, transport=httpx.MockTransport(wompi))
    return PasarelaWompi(_configuracion(), cliente)


def _tarjeta() -> SolicitudCobro:
    return SolicitudCobro(
        referencia="ALQ-1-ABCD",
        monto=90_000,
        metodo="tarjeta",
        correo="cliente@prueba.co",
        descripcion="TransportExperience alquiler #1",
        tarjeta=DatosTarjeta("tok_test_1", 1),
    )


def test_cobro_con_tarjeta_envia_lo_que_pide_wompi(monkeypatch) -> None:
    wompi = Wompi(
        {
            ("GET", "/v1/merchants/info"): (200, COMERCIO),
            ("POST", "/v1/transactions"): (201, {"data": {"id": "tx-1", "status": "APPROVED"}}),
        }
    )

    resultado = _pasarela(wompi).cobrar(_tarjeta())

    assert (resultado.estado, resultado.id_transaccion) == (EstadoPago.APROBADO, "tx-1")
    comercio, cobro = wompi.solicitudes
    assert comercio.headers["x-merchant-public-key"] == "pub_test_abc123"
    assert cobro.headers["authorization"] == "Bearer pub_test_abc123"
    cuerpo = json.loads(cobro.content)
    assert cuerpo["amount_in_cents"] == 9_000_000  # pesos a centavos
    assert cuerpo["currency"] == "COP"
    assert cuerpo["reference"] == "ALQ-1-ABCD"
    assert cuerpo["signature"] == firma_integridad("ALQ-1-ABCD", 9_000_000, "test_integrity_abc123")
    assert (cuerpo["acceptance_token"], cuerpo["accept_personal_auth"]) == (
        "tok-terminos",
        "tok-datos",
    )
    assert cuerpo["payment_method"] == {"type": "CARD", "token": "tok_test_1", "installments": 1}


def test_cobro_pse_queda_pendiente_con_la_url_del_banco() -> None:
    con_url = {
        "id": "tx-2",
        "status": "PENDING",
        "payment_method": {"extra": {"async_payment_url": "https://banco.test/pagar"}},
    }
    wompi = Wompi(
        {
            ("GET", "/v1/merchants/info"): (200, COMERCIO),
            ("POST", "/v1/transactions"): (201, {"data": {"id": "tx-2", "status": "PENDING"}}),
            ("GET", "/v1/transactions/tx-2"): (200, {"data": con_url}),
        }
    )
    solicitud = SolicitudCobro(
        "VEN-1-ABCD",
        50_000,
        "pse",
        "c@prueba.co",
        "Compra",
        pse=DatosPse("natural", "CC", "123456", "1"),
    )

    resultado = _pasarela(wompi).cobrar(solicitud)

    assert resultado.estado == EstadoPago.PENDIENTE
    assert resultado.url_redireccion == "https://banco.test/pagar"
    metodo = json.loads(wompi.solicitudes[1].content)["payment_method"]
    assert metodo["type"] == "PSE"
    assert (metodo["user_type"], metodo["financial_institution_code"]) == (0, "1")


def test_si_wompi_rechaza_la_solicitud_el_cobro_queda_en_error() -> None:
    error = {"error": {"type": "INPUT_VALIDATION_ERROR", "messages": {"token": ["inválido"]}}}
    wompi = Wompi(
        {
            ("GET", "/v1/merchants/info"): (200, COMERCIO),
            ("POST", "/v1/transactions"): (422, error),
        }
    )
    resultado = _pasarela(wompi).cobrar(_tarjeta())
    assert resultado.estado == EstadoPago.ERROR
    assert "token" in resultado.detalle


@pytest.mark.parametrize(
    "falla", [httpx.ReadTimeout("lento"), httpx.ConnectError("sin red")], ids=["timeout", "red"]
)
def test_si_wompi_no_responde_se_avisa_sin_inventar_un_resultado(falla) -> None:
    wompi = Wompi(
        {("GET", "/v1/merchants/info"): (200, COMERCIO), ("POST", "/v1/transactions"): falla}
    )
    with pytest.raises(PasarelaNoDisponible):
        _pasarela(wompi).cobrar(_tarjeta())


def test_error_500_de_wompi_tampoco_inventa_un_resultado() -> None:
    wompi = Wompi(
        {("GET", "/v1/merchants/info"): (200, COMERCIO), ("POST", "/v1/transactions"): (503, {})}
    )
    with pytest.raises(PasarelaNoDisponible):
        _pasarela(wompi).cobrar(_tarjeta())


def test_consulta_de_respaldo_usa_la_llave_privada_y_la_referencia() -> None:
    wompi = Wompi(
        {("GET", "/v1/transactions"): (200, {"data": [{"id": "tx-1", "status": "DECLINED"}]})}
    )

    resultado = _pasarela(wompi).consultar("ALQ-1-ABCD")

    assert resultado.estado == EstadoPago.RECHAZADO
    [solicitud] = wompi.solicitudes
    assert solicitud.headers["authorization"] == "Bearer prv_test_abc123"
    assert solicitud.url.params["reference"] == "ALQ-1-ABCD"


def test_consulta_de_una_referencia_que_wompi_no_conoce() -> None:
    wompi = Wompi({("GET", "/v1/transactions"): (200, {"data": []})})
    assert _pasarela(wompi).consultar("ALQ-9-XXXX") is None


def test_los_tokens_de_aceptacion_se_reutilizan() -> None:
    aprobado = (201, {"data": {"id": "tx", "status": "APPROVED"}})
    wompi = Wompi(
        {
            ("GET", "/v1/merchants/info"): (200, COMERCIO),
            ("POST", "/v1/transactions"): [aprobado, aprobado],
        }
    )
    pasarela = _pasarela(wompi)
    pasarela.cobrar(_tarjeta())
    pasarela.cobrar(_tarjeta())
    rutas = [s.url.path for s in wompi.solicitudes]
    assert rutas.count("/v1/merchants/info") == 1
