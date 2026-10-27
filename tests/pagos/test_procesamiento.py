"""Cobro en dos fases, pagos pendientes, webhook y devoluciones (HU-05, CLAUDE.md 7.3).

Contra Postgres, con la pasarela falsa (sin red) y "ahora" fijo.
"""

import hashlib
import json
import os
import time
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.comun.errores import PermisoDenegado
from app.comun.paginacion import ParametrosPagina
from app.modulos.alquileres import servicio as alquileres
from app.modulos.alquileres.excepciones import AlquilerNoCancelable, SinUnidadesDisponibles
from app.modulos.alquileres.modelos import Alquiler, EstadoAlquiler
from app.modulos.pagos import procesamiento
from app.modulos.pagos.comprobante import datos_comprobante, generar_pdf, pesos
from app.modulos.pagos.esquemas import PagoCrear
from app.modulos.pagos.excepciones import (
    DatosDePagoIncompletos,
    DevolucionNoPendiente,
    PagoEnCurso,
    PasarelaNoDisponible,
    TerminosNoAceptados,
)
from app.modulos.pagos.modelos import EstadoPago, EventoPago, MetodoPago, Pago, TipoPago
from app.modulos.pagos.pasarela import PasarelaFalsa, ResultadoCobro
from app.modulos.usuarios.modelos import Rol
from app.modulos.ventas import servicio as ventas
from app.modulos.ventas.esquemas import VentaCrear
from app.modulos.ventas.modelos import EstadoVenta

HOY = date(2026, 11, 2)
MOMENTO = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
TARJETA = PagoCrear(metodo_pago="tarjeta")
SECRETO = os.environ["WOMPI_SECRETO_EVENTOS"]


def minutos(n: int) -> datetime:
    return MOMENTO + timedelta(minutes=n)


@pytest.fixture(autouse=True)
def metodos_pago(sesion) -> None:
    sesion.add_all(
        [MetodoPago(codigo="tarjeta", nombre="Tarjeta"), MetodoPago(codigo="pse", nombre="PSE")]
    )
    sesion.flush()


@pytest.fixture
def modelo(fabrica):
    modelo = fabrica.modelo(tarifa_diaria=30_000, precio_venta=900_000)
    fabrica.vehiculo(modelo)  # una sola unidad
    return modelo


@pytest.fixture
def cliente(fabrica):
    return fabrica.cliente()


@pytest.fixture
def alquiler(sesion, modelo, cliente) -> Alquiler:
    inicio = HOY + timedelta(days=3)
    return alquileres.crear_alquiler(
        sesion, cliente, modelo.id, inicio, inicio + timedelta(days=2), hoy=HOY, momento=MOMENTO
    )


def _pagar(
    sesion, cliente, pasarela, *, alquiler_id=None, venta_id=None, datos=TARJETA, momento=MOMENTO
):
    return procesamiento.pagar(
        sesion,
        cliente,
        datos,
        pasarela,
        alquiler_id=alquiler_id,
        venta_id=venta_id,
        momento=momento,
    )


def _reportar(sesion, pago: Pago, estado: EstadoPago, momento: datetime):
    return procesamiento.aplicar_resultado(sesion, pago.id, ResultadoCobro(estado, "tx-1"), momento)


# --- Dos fases (decisión 2) --------------------------------------------------------------


class PasarelaEspia(PasarelaFalsa):
    """Al cobrar, anota cómo estaban el pago y el alquiler en la base en ese instante."""

    def __init__(self, sesion) -> None:
        super().__init__()
        self.sesion = sesion
        self.visto: tuple | None = None

    def cobrar(self, solicitud):
        pago = self.sesion.scalars(
            select(Pago).where(Pago.referencia == solicitud.referencia)
        ).one()
        alquiler = self.sesion.get(Alquiler, pago.alquiler_id)
        self.visto = (pago.estado, alquiler.estado, alquiler.expira_en)
        return super().cobrar(solicitud)


def test_el_pago_se_guarda_pendiente_antes_de_llamar_a_la_pasarela(
    sesion, alquiler, cliente
) -> None:
    espia = PasarelaEspia(sesion)

    resultado = _pagar(sesion, cliente, espia, alquiler_id=alquiler.id)

    assert espia.visto == (EstadoPago.PENDIENTE, EstadoAlquiler.PENDIENTE_PAGO, minutos(60))
    assert resultado.pago.estado == EstadoPago.APROBADO
    assert alquiler.estado == EstadoAlquiler.CONFIRMADO
    assert resultado.pago.bloqueo_original_hasta == minutos(15)


class PasarelaCaida(PasarelaFalsa):
    def cobrar(self, solicitud):
        raise PasarelaNoDisponible()


def test_si_la_pasarela_no_responde_el_pago_queda_pendiente_y_se_resuelve_con_el_respaldo(
    sesion, alquiler, cliente
) -> None:
    resultado = _pagar(sesion, cliente, PasarelaCaida(), alquiler_id=alquiler.id)

    assert resultado.pago.estado == EstadoPago.PENDIENTE
    assert alquiler.estado == EstadoAlquiler.PENDIENTE_PAGO

    procesamiento.sincronizar(
        sesion, resultado.pago, PasarelaFalsa(consulta=EstadoPago.APROBADO), minutos(3)
    )

    assert resultado.pago.estado == EstadoPago.APROBADO
    assert alquiler.estado == EstadoAlquiler.CONFIRMADO


def test_la_consulta_de_respaldo_no_cambia_nada_si_la_pasarela_no_conoce_la_referencia(
    sesion, alquiler, cliente
) -> None:
    pago = _pagar(sesion, cliente, PasarelaCaida(), alquiler_id=alquiler.id).pago
    procesamiento.sincronizar(sesion, pago, PasarelaFalsa(consulta=None), minutos(3))
    assert pago.estado == EstadoPago.PENDIENTE


# --- Pago pendiente: el bloqueo no vence (decisión 1) ------------------------------------


@pytest.fixture
def pendiente(sesion, alquiler, cliente) -> Pago:
    """Un PSE que queda pendiente en el minuto 0."""
    return _pagar(
        sesion, cliente, PasarelaFalsa(EstadoPago.PENDIENTE), alquiler_id=alquiler.id
    ).pago


def test_con_pago_pendiente_la_reserva_sigue_bloqueando_despues_de_15_minutos(
    sesion, pendiente, alquiler, modelo, crear_usuario
) -> None:
    assert alquiler.expira_en == minutos(60)
    otro = crear_usuario(Rol.CLIENTE)
    with pytest.raises(SinUnidadesDisponibles):
        alquileres.crear_alquiler(
            sesion,
            otro,
            modelo.id,
            alquiler.fecha_inicio,
            alquiler.fecha_fin,
            hoy=HOY,
            momento=minutos(30),
        )
    assert alquiler.estado == EstadoAlquiler.PENDIENTE_PAGO


def test_el_maximo_de_minutos_con_pago_pendiente_se_lee_de_la_base(
    sesion, alquiler, cliente
) -> None:
    from app.parametros import MAX_MINUTOS_PAGO_PENDIENTE, ParametroSistema

    sesion.get(ParametroSistema, MAX_MINUTOS_PAGO_PENDIENTE).valor = 20
    sesion.flush()
    _pagar(sesion, cliente, PasarelaFalsa(EstadoPago.PENDIENTE), alquiler_id=alquiler.id)
    assert alquiler.expira_en == minutos(20)


def test_rechazo_dentro_del_plazo_original_vuelve_a_los_15_minutos(
    sesion, pendiente, alquiler
) -> None:
    _reportar(sesion, pendiente, EstadoPago.RECHAZADO, minutos(5))

    assert pendiente.estado == EstadoPago.RECHAZADO
    assert alquiler.estado == EstadoAlquiler.PENDIENTE_PAGO
    assert alquiler.expira_en == minutos(15)


@pytest.mark.parametrize("estado", [EstadoPago.RECHAZADO, EstadoPago.EXPIRADO, EstadoPago.ERROR])
def test_falla_despues_del_plazo_original_expira_la_reserva(
    sesion, pendiente, alquiler, estado
) -> None:
    _reportar(sesion, pendiente, estado, minutos(20))
    assert alquiler.estado == EstadoAlquiler.EXPIRADO


def test_tras_el_maximo_con_pago_pendiente_la_reserva_expira(
    sesion, pendiente, alquiler, modelo, crear_usuario
) -> None:
    otro = crear_usuario(Rol.CLIENTE)
    nuevo = alquileres.crear_alquiler(
        sesion,
        otro,
        modelo.id,
        alquiler.fecha_inicio,
        alquiler.fecha_fin,
        hoy=HOY,
        momento=minutos(61),
    )
    assert alquiler.estado == EstadoAlquiler.EXPIRADO
    assert nuevo.vehiculo_id == alquiler.vehiculo_id


def test_pago_aprobado_despues_de_expirar_se_devuelve(sesion, pendiente, alquiler) -> None:
    devolucion = _reportar(sesion, pendiente, EstadoPago.APROBADO, minutos(61))

    assert pendiente.estado == EstadoPago.APROBADO  # el cobro aprobado no se toca
    assert alquiler.estado == EstadoAlquiler.EXPIRADO
    assert devolucion.tipo == TipoPago.COMPENSACION
    assert devolucion.pago_compensado_id == pendiente.id
    assert devolucion.estado == EstadoPago.PENDIENTE
    pendientes = procesamiento.listar_devoluciones_pendientes(sesion, ParametrosPagina())
    assert [p.id for p in pendientes.elementos] == [devolucion.id]


def test_aviso_repetido_no_cambia_un_pago_resuelto(sesion, pendiente, alquiler) -> None:
    _reportar(sesion, pendiente, EstadoPago.APROBADO, minutos(5))
    devolucion = _reportar(sesion, pendiente, EstadoPago.APROBADO, minutos(6))
    _reportar(sesion, pendiente, EstadoPago.RECHAZADO, minutos(7))

    assert devolucion is None
    assert pendiente.estado == EstadoPago.APROBADO
    assert alquiler.estado == EstadoAlquiler.CONFIRMADO


def test_no_hay_dos_pagos_en_curso_ni_se_cancela_con_uno_pendiente(
    sesion, pendiente, alquiler, cliente
) -> None:
    with pytest.raises(PagoEnCurso):
        _pagar(sesion, cliente, PasarelaFalsa(), alquiler_id=alquiler.id, momento=minutos(1))
    with pytest.raises(PagoEnCurso):
        alquileres.cancelar_alquiler(sesion, alquiler.id, cliente, momento=minutos(1))


# --- Ventas -------------------------------------------------------------------------------


@pytest.fixture
def venta(sesion, fabrica, cliente):
    casco = fabrica.producto(stock=1)
    venta = ventas.crear_venta(
        sesion, cliente, VentaCrear(productos=[{"producto_id": casco.id}]), momento=MOMENTO
    )
    return venta, casco


def test_compra_con_pse_rechazado_tarde_devuelve_el_stock(sesion, venta, cliente) -> None:
    venta, casco = venta
    pago = _pagar(sesion, cliente, PasarelaFalsa(EstadoPago.PENDIENTE), venta_id=venta.id).pago
    assert venta.expira_en == minutos(60)

    _reportar(sesion, pago, EstadoPago.RECHAZADO, minutos(20))

    assert venta.estado == EstadoVenta.EXPIRADA
    assert casco.stock == 1


def test_compra_aprobada_despues_de_expirar_se_devuelve(sesion, venta, cliente) -> None:
    venta, casco = venta
    pago = _pagar(sesion, cliente, PasarelaFalsa(EstadoPago.PENDIENTE), venta_id=venta.id).pago

    devolucion = _reportar(sesion, pago, EstadoPago.APROBADO, minutos(61))

    assert venta.estado == EstadoVenta.EXPIRADA
    assert casco.stock == 1
    assert devolucion.monto == pago.monto


# --- Validación con una pasarela real ------------------------------------------------------


class PasarelaReal(PasarelaFalsa):
    nombre = "wompi"


def test_con_wompi_hay_que_aceptar_los_terminos(sesion, alquiler, cliente) -> None:
    with pytest.raises(TerminosNoAceptados):
        _pagar(sesion, cliente, PasarelaReal(), alquiler_id=alquiler.id)


def test_con_wompi_la_tarjeta_necesita_su_token(sesion, alquiler, cliente) -> None:
    datos = PagoCrear(metodo_pago="tarjeta", acepta_terminos=True)
    with pytest.raises(DatosDePagoIncompletos):
        _pagar(sesion, cliente, PasarelaReal(), alquiler_id=alquiler.id, datos=datos)


def test_la_pasarela_recibe_los_datos_del_metodo(sesion, alquiler, cliente) -> None:
    pasarela = PasarelaReal()
    datos = PagoCrear(
        metodo_pago="pse",
        acepta_terminos=True,
        pse={"documento": "1098765432", "banco": "1"},
    )
    _pagar(sesion, cliente, pasarela, alquiler_id=alquiler.id, datos=datos)
    [solicitud] = pasarela.solicitudes
    assert (solicitud.metodo, solicitud.pse.banco, solicitud.correo) == ("pse", "1", cliente.correo)


def test_responde_en_menos_de_3_segundos(sesion, alquiler, cliente) -> None:
    inicio = time.perf_counter()
    _pagar(sesion, cliente, PasarelaFalsa(), alquiler_id=alquiler.id)
    assert time.perf_counter() - inicio < 3  # HU-05 (con la falsa, mide lo nuestro)


# --- Webhook ------------------------------------------------------------------------------


def _evento(pago: Pago, estado: str, *, monto=None, ambiente="test", secreto=SECRETO) -> bytes:
    transaccion = {
        "id": "tx-99",
        "status": estado,
        "amount_in_cents": pago.monto * 100 if monto is None else monto,
        "reference": pago.referencia,
    }
    marca = 1_798_000_000
    valores = f"{transaccion['id']}{estado}{transaccion['amount_in_cents']}"
    checksum = hashlib.sha256(f"{valores}{marca}{secreto}".encode()).hexdigest().upper()
    return json.dumps(
        {
            "event": "transaction.updated",
            "data": {"transaction": transaccion},
            "environment": ambiente,
            "signature": {
                "properties": [
                    "transaction.id",
                    "transaction.status",
                    "transaction.amount_in_cents",
                ],
                "checksum": checksum,
            },
            "timestamp": marca,
        }
    ).encode()


def _webhook(sesion, cuerpo: bytes) -> EventoPago:
    return procesamiento.procesar_evento_wompi(sesion, cuerpo, SECRETO, momento=minutos(5))


def test_webhook_aprobado_confirma_y_guarda_el_cuerpo_crudo(sesion, pendiente, alquiler) -> None:
    cuerpo = _evento(pendiente, "APPROVED")

    evento = _webhook(sesion, cuerpo)

    assert (evento.firma_valida, evento.procesado, evento.error) == (True, True, None)
    assert evento.cuerpo_crudo == cuerpo.decode()
    assert evento.clave_idempotencia == "tx-99:APPROVED"
    assert pendiente.estado == EstadoPago.APROBADO
    assert alquiler.estado == EstadoAlquiler.CONFIRMADO


def test_webhook_repetido_se_guarda_pero_no_se_procesa(sesion, pendiente) -> None:
    _webhook(sesion, _evento(pendiente, "APPROVED"))

    repetido = _webhook(sesion, _evento(pendiente, "APPROVED"))

    assert (repetido.procesado, repetido.clave_idempotencia) == (False, None)
    assert "repetido" in repetido.error
    assert len(sesion.scalars(select(EventoPago)).all()) == 2


@pytest.mark.parametrize(
    ("cuerpo", "error"),
    [
        (lambda p: _evento(p, "APPROVED", secreto="test_events_falso"), "Firma inválida"),
        (lambda p: _evento(p, "APPROVED", monto=1), "monto"),
        (lambda p: _evento(p, "APPROVED", ambiente="prod"), "sandbox"),
        (lambda p: b"{no es json", "JSON"),
    ],
    ids=["firma", "monto", "produccion", "json"],
)
def test_webhook_que_no_se_procesa(sesion, pendiente, alquiler, cuerpo, error) -> None:
    evento = _webhook(sesion, cuerpo(pendiente))

    assert not evento.procesado
    assert error in evento.error
    assert pendiente.estado == EstadoPago.PENDIENTE
    assert alquiler.estado == EstadoAlquiler.PENDIENTE_PAGO


def test_un_evento_falso_no_bloquea_al_verdadero(sesion, pendiente) -> None:
    _webhook(sesion, _evento(pendiente, "APPROVED", secreto="test_events_falso"))
    verdadero = _webhook(sesion, _evento(pendiente, "APPROVED"))
    assert verdadero.procesado


# --- Cancelación con devolución y devoluciones ---------------------------------------------


def test_el_administrador_cancela_un_alquiler_pagado_con_devolucion(
    sesion, alquiler, cliente, crear_usuario
) -> None:
    cobro = _pagar(sesion, cliente, PasarelaFalsa(), alquiler_id=alquiler.id).pago
    administrador = crear_usuario(Rol.ADMINISTRADOR)

    _, devolucion = alquileres.cancelar_con_devolucion(
        sesion, alquiler.id, administrador, "La unidad quedó en mantenimiento."
    )

    assert alquiler.estado == EstadoAlquiler.CANCELADO
    assert alquiler.motivo_cancelacion == "La unidad quedó en mantenimiento."
    assert (devolucion.pago_compensado_id, devolucion.monto) == (cobro.id, cobro.monto)

    procesamiento.marcar_devolucion_ejecutada(
        sesion, devolucion.referencia, administrador, "Reembolso hecho en el panel."
    )
    assert devolucion.estado == EstadoPago.APROBADO
    with pytest.raises(DevolucionNoPendiente):
        procesamiento.marcar_devolucion_ejecutada(
            sesion, devolucion.referencia, administrador, "Otra vez."
        )


def test_solo_el_administrador_cancela_con_devolucion(
    sesion, alquiler, cliente, crear_usuario
) -> None:
    _pagar(sesion, cliente, PasarelaFalsa(), alquiler_id=alquiler.id)
    with pytest.raises(PermisoDenegado):
        alquileres.cancelar_con_devolucion(
            sesion, alquiler.id, crear_usuario(Rol.OPERADOR), "Motivo."
        )


def test_sin_pagar_no_hay_cancelacion_con_devolucion(sesion, alquiler, crear_usuario) -> None:
    with pytest.raises(AlquilerNoCancelable):
        alquileres.cancelar_con_devolucion(
            sesion, alquiler.id, crear_usuario(Rol.ADMINISTRADOR), "Motivo."
        )


# --- Comprobante en PDF --------------------------------------------------------------------


def test_comprobante_de_un_alquiler(sesion, alquiler, cliente) -> None:
    pago = _pagar(sesion, cliente, PasarelaFalsa(), alquiler_id=alquiler.id).pago

    datos = datos_comprobante(sesion, pago)

    assert datos.servicio == f"Alquiler #{alquiler.id}"
    assert datos.cliente_correo == cliente.correo
    assert datos.total == 90_000 == sum(linea.valor for linea in datos.lineas)
    assert "3 día(s)" in datos.lineas[0].descripcion
    assert datos.estado == EstadoPago.APROBADO
    assert generar_pdf(datos).startswith(b"%PDF")


def test_comprobante_de_una_compra(sesion, venta, cliente) -> None:
    venta, casco = venta
    pago = _pagar(sesion, cliente, PasarelaFalsa(), venta_id=venta.id).pago

    datos = datos_comprobante(sesion, pago)

    assert datos.servicio == f"Compra #{venta.id}"
    assert casco.codigo in datos.lineas[0].descripcion
    assert generar_pdf(datos).startswith(b"%PDF")


def test_formato_de_pesos() -> None:
    assert pesos(1_234_567) == "$1.234.567"
