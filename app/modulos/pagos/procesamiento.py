"""Orquestación de los pagos (HU-05, CLAUDE.md 7.3): cobro, webhook y consulta de respaldo.

**Cobro en dos fases** (decisión 2 de HU-05):

1. Con la operación bloqueada, se guarda el pago ``pendiente`` y se **confirma** en la base.
2. Fuera de toda transacción, se llama a la pasarela. Si no responde, el pago se queda
   ``pendiente``: nunca hay un cobro en la pasarela sin registro aquí.
3. Se aplica el resultado (``aplicar_resultado``), con la operación bloqueada otra vez.

**La verdad del pago la da la pasarela, no el navegador**: el paso 3 también lo disparan
el webhook (``procesar_evento_wompi``) y la consulta de respaldo a la API de Wompi
(``sincronizar``), necesaria en desarrollo porque Wompi no puede llegar a 127.0.0.1.
Los tres caminos son idempotentes: un pago ya resuelto no cambia.

Vive aparte de ``servicio.py`` porque usa los servicios de alquileres y ventas, que a su
vez usan ``servicio.py``.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auditoria import registrar_auditoria
from app.comun import fechas
from app.comun.errores import PermisoDenegado
from app.comun.paginacion import ParametrosPagina, ResultadoPagina, paginar
from app.modulos.alquileres import servicio as alquileres
from app.modulos.alquileres.modelos import Alquiler
from app.modulos.pagos import servicio as pagos
from app.modulos.pagos.esquemas import PagoCrear
from app.modulos.pagos.excepciones import (
    DatosDePagoIncompletos,
    DevolucionNoPendiente,
    PagoNoEncontrado,
    PasarelaNoDisponible,
    TerminosNoAceptados,
)
from app.modulos.pagos.modelos import EstadoPago, EventoPago, Pago, TipoPago
from app.modulos.pagos.pasarela import (
    DatosPse,
    DatosTarjeta,
    PasarelaPagos,
    ResultadoCobro,
    SolicitudCobro,
)
from app.modulos.pagos.wompi import resultado_de_transaccion, verificar_firma_evento
from app.modulos.usuarios.modelos import Rol, Usuario
from app.modulos.ventas import servicio as ventas
from app.modulos.ventas.modelos import Venta

registro = logging.getLogger(__name__)

ROLES_DE_MOSTRADOR = frozenset({Rol.ADMINISTRADOR, Rol.OPERADOR})


@dataclass(frozen=True)
class ResultadoPago:
    pago: Pago
    devolucion: Pago | None


# --- Cobro ----------------------------------------------------------------------------------


def _validar_datos(datos: PagoCrear, pasarela: PasarelaPagos) -> None:
    """Con una pasarela real, exige términos aceptados y los datos del método."""
    if pasarela.nombre == "falso":
        return
    if not datos.acepta_terminos:
        raise TerminosNoAceptados()
    if datos.metodo_pago == "tarjeta" and datos.tarjeta is None:
        raise DatosDePagoIncompletos("Para pagar con tarjeta falta `tarjeta.token`.")
    if datos.metodo_pago == "pse" and datos.pse is None:
        raise DatosDePagoIncompletos("Para pagar con PSE faltan los datos de `pse`.")


def _solicitud(pago: Pago, datos: PagoCrear, cliente: Usuario) -> SolicitudCobro:
    operacion = f"alquiler #{pago.alquiler_id}" if pago.alquiler_id else f"compra #{pago.venta_id}"
    return SolicitudCobro(
        referencia=pago.referencia,
        monto=pago.monto,
        metodo=datos.metodo_pago,
        correo=cliente.correo,
        descripcion=f"TransportExperience {operacion}",
        tarjeta=DatosTarjeta(datos.tarjeta.token, datos.tarjeta.cuotas) if datos.tarjeta else None,
        pse=DatosPse(**datos.pse.model_dump()) if datos.pse else None,
    )


def pagar(
    sesion: Session,
    cliente: Usuario,
    datos: PagoCrear,
    pasarela: PasarelaPagos,
    *,
    alquiler_id: int | None = None,
    venta_id: int | None = None,
    momento: datetime | None = None,
) -> ResultadoPago:
    """Cobra un alquiler o una compra en tres pasos (ver el docstring del módulo)."""
    _validar_datos(datos, pasarela)
    momento = momento or fechas.ahora()
    if alquiler_id is not None:
        pago = alquileres.preparar_pago(
            sesion, alquiler_id, cliente, datos.metodo_pago, pasarela.nombre, momento=momento
        )
    else:
        pago = ventas.preparar_pago(
            sesion, venta_id, cliente, datos.metodo_pago, pasarela.nombre, momento=momento
        )

    try:
        resultado = pasarela.cobrar(_solicitud(pago, datos, cliente))
    except PasarelaNoDisponible:
        # No se sabe si Wompi creó el cobro: queda pendiente y lo resuelve el respaldo.
        resultado = ResultadoCobro(EstadoPago.PENDIENTE)

    devolucion = aplicar_resultado(sesion, pago.id, resultado, momento)
    sesion.refresh(pago)
    return ResultadoPago(pago, devolucion)


def aplicar_resultado(
    sesion: Session, pago_id: int, resultado: ResultadoCobro, momento: datetime
) -> Pago | None:
    """Aplica lo que reporta la pasarela al pago y a su operación. Idempotente."""
    alquiler_id = sesion.scalar(select(Pago.alquiler_id).where(Pago.id == pago_id))
    if alquiler_id is not None:
        return alquileres.aplicar_resultado_pago(sesion, pago_id, resultado, momento)
    return ventas.aplicar_resultado_pago(sesion, pago_id, resultado, momento)


def sincronizar(
    sesion: Session, pago: Pago, pasarela: PasarelaPagos, momento: datetime | None = None
) -> Pago:
    """Consulta de respaldo: si el cobro sigue pendiente, le pregunta a la pasarela."""
    if (
        pago.estado != EstadoPago.PENDIENTE
        or pago.tipo != TipoPago.COBRO
        or pago.proveedor != pasarela.nombre
    ):
        return pago
    try:
        resultado = pasarela.consultar(pago.referencia)
    except PasarelaNoDisponible:
        return pago  # se intentará en la próxima consulta
    if resultado is not None:
        aplicar_resultado(sesion, pago.id, resultado, momento or fechas.ahora())
        sesion.refresh(pago)
    return pago


# --- Webhook de Wompi -----------------------------------------------------------------------


def procesar_evento_wompi(
    sesion: Session, cuerpo: bytes, secreto: str, *, momento: datetime | None = None
) -> EventoPago:
    """Procesa un evento de Wompi. Siempre guarda el cuerpo crudo (CLAUDE.md 7.3).

    Solo se procesa si la firma es válida, es del sandbox, es de una transacción nuestra y
    el monto coincide. La ``clave_idempotencia`` (id de transacción + estado) solo se llena
    con firma válida, así un evento falso no bloquea al verdadero; un repetido se guarda y
    se descarta.
    """
    texto = cuerpo.decode("utf-8", errors="replace")
    evento = EventoPago(proveedor="wompi", cuerpo_crudo=texto, firma_valida=False)
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        datos = None
    if not isinstance(datos, dict):
        return _guardar_evento(sesion, evento, "El cuerpo no es un JSON válido.")

    evento.firma_valida = verificar_firma_evento(datos, secreto)
    transaccion = (datos.get("data") or {}).get("transaction") or {}
    evento.estado_reportado = str(transaccion.get("status"))[:30]
    if not evento.firma_valida:
        return _guardar_evento(sesion, evento, "Firma inválida: se ignora.")
    if datos.get("environment") != "test":
        return _guardar_evento(sesion, evento, "Evento fuera del sandbox: se ignora.")
    if datos.get("event") != "transaction.updated":
        return _guardar_evento(sesion, evento, "Tipo de evento que no usamos.")

    evento.clave_idempotencia = f"{transaccion.get('id')}:{transaccion.get('status')}"
    pago = sesion.scalars(
        select(Pago).where(Pago.referencia == str(transaccion.get("reference")))
    ).one_or_none()
    error = None
    if pago is None:
        error = "La referencia no corresponde a ningún pago."
    elif transaccion.get("amount_in_cents") != pago.monto * 100:
        error = "El monto no coincide con el del pago: no se procesa."
    evento.pago_id = pago.id if pago else None
    try:
        _guardar_evento(sesion, evento, error)
    except IntegrityError:
        sesion.rollback()
        evento = EventoPago(
            proveedor="wompi",
            cuerpo_crudo=texto,
            firma_valida=True,
            estado_reportado=str(transaccion.get("status"))[:30],
            pago_id=pago.id if pago else None,
        )
        return _guardar_evento(sesion, evento, "Evento repetido: ya se había recibido.")
    if error:
        return evento

    aplicar_resultado(
        sesion, pago.id, resultado_de_transaccion(transaccion), momento or fechas.ahora()
    )
    evento = sesion.get(EventoPago, evento.id)
    evento.procesado = True
    sesion.commit()
    return evento


def _guardar_evento(sesion: Session, evento: EventoPago, error: str | None) -> EventoPago:
    evento.error = error
    sesion.add(evento)
    sesion.commit()
    if error:
        registro.warning(
            "Evento de pago descartado", extra={"evento_id": evento.id, "error": error}
        )
    return evento


# --- Consultas, devoluciones -----------------------------------------------------------------


def obtener_pago(sesion: Session, referencia: str, usuario: Usuario) -> Pago:
    """Un pago. El cliente solo ve los de sus operaciones; el mostrador, todos."""
    pago = sesion.scalars(select(Pago).where(Pago.referencia == referencia)).one_or_none()
    if pago is None:
        raise PagoNoEncontrado()
    if usuario.rol == Rol.CLIENTE:
        if cliente_del_pago(sesion, pago) != usuario.id:
            raise PagoNoEncontrado()
    elif usuario.rol not in ROLES_DE_MOSTRADOR:
        raise PermisoDenegado()
    return pago


def cliente_del_pago(sesion: Session, pago: Pago) -> int:
    if pago.alquiler_id is not None:
        return sesion.scalar(select(Alquiler.cliente_id).where(Alquiler.id == pago.alquiler_id))
    return sesion.scalar(select(Venta.cliente_id).where(Venta.id == pago.venta_id))


def listar_devoluciones_pendientes(
    sesion: Session, parametros: ParametrosPagina
) -> ResultadoPagina:
    """Devoluciones registradas y aún sin ejecutar, de alquileres y de compras."""
    consulta = (
        select(Pago)
        .where(Pago.tipo == TipoPago.COMPENSACION, Pago.estado == EstadoPago.PENDIENTE)
        .order_by(Pago.id)
    )
    return paginar(sesion, consulta, parametros)


def marcar_devolucion_ejecutada(
    sesion: Session, referencia: str, administrador: Usuario, nota: str
) -> Pago:
    """El administrador hizo el reembolso en el panel de Wompi y lo deja registrado."""
    if administrador.rol != Rol.ADMINISTRADOR:
        raise PermisoDenegado()
    pago_id = sesion.scalar(select(Pago.id).where(Pago.referencia == referencia))
    if pago_id is None:
        raise PagoNoEncontrado()
    pago = pagos.bloquear_pago(sesion, pago_id)
    if pago.tipo != TipoPago.COMPENSACION or pago.estado != EstadoPago.PENDIENTE:
        raise DevolucionNoPendiente()
    pago.estado = EstadoPago.APROBADO
    pago.aprobado_en = fechas.ahora()
    pago.detalle_error = f"{pago.detalle_error or ''} | Ejecutada: {nota}".strip(" |")
    registrar_auditoria(
        sesion,
        usuario_id=administrador.id,
        accion="ejecutar_devolucion",
        entidad="pagos",
        entidad_id=pago.id,
        antes={"estado": "pendiente"},
        despues={"estado": "aprobado", "nota": nota},
    )
    sesion.commit()
    return pago


def cobros_pendientes(sesion: Session, proveedor: str) -> list[int]:
    """Ids de los cobros que esperan respuesta de la pasarela (para el barrido manual)."""
    return list(
        sesion.scalars(
            select(Pago.id)
            .where(
                Pago.tipo == TipoPago.COBRO,
                Pago.estado == EstadoPago.PENDIENTE,
                Pago.proveedor == proveedor,
            )
            .order_by(Pago.id)
        )
    )
