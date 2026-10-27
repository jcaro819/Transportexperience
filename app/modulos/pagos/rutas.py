"""Rutas de pagos (HU-05).

El cobro mismo se inicia desde la operación (``POST /alquileres/{id}/pago`` y
``POST /ventas/{id}/pago``). Aquí están la configuración para el frontend, la consulta del
estado (con consulta de respaldo a la pasarela), el comprobante en PDF, el webhook de Wompi
y las devoluciones.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select

from app.comun.errores import respuestas_error
from app.comun.paginacion import Pagina, Paginacion
from app.comun.peticiones import leer_cuerpo_limitado
from app.config import obtener_configuracion
from app.db import SesionBD
from app.modulos.pagos import procesamiento
from app.modulos.pagos.comprobante import datos_comprobante, generar_pdf
from app.modulos.pagos.esquemas import (
    BancoPse,
    ConfiguracionPagos,
    DevolucionEjecutada,
    EventoRecibido,
    PagoDetalle,
)
from app.modulos.pagos.modelos import MetodoPago
from app.modulos.pagos.pasarela import PasarelaPagos, obtener_pasarela
from app.seguridad import SoloAdministrador, UsuarioActual

enrutador_pagos = APIRouter(prefix="/pagos", tags=["pagos"])

# Un evento real de Wompi pesa unos pocos KiB; 64 KiB deja margen de sobra.
LIMITE_CUERPO_WEBHOOK = 64 * 1024

Pasarela = Annotated[PasarelaPagos, Depends(obtener_pasarela)]


@enrutador_pagos.get(
    "/configuracion",
    response_model=ConfiguracionPagos,
    summary="Configuración de pagos para el frontend",
    responses=respuestas_error(),
)
def configuracion(sesion: SesionBD, pasarela: Pasarela) -> ConfiguracionPagos:
    """Métodos habilitados y, con Wompi, la llave pública para tokenizar la tarjeta y los
    enlaces de términos y autorización de datos que el cliente debe aceptar.
    """
    publica = pasarela.configuracion_publica()
    metodos = sesion.scalars(
        select(MetodoPago.codigo).where(MetodoPago.activo).order_by(MetodoPago.codigo)
    ).all()
    return ConfiguracionPagos(
        proveedor=publica.proveedor,
        metodos=list(metodos),
        llave_publica=publica.llave_publica,
        url_api=publica.url_api,
        terminos_url=publica.terminos_url,
        datos_personales_url=publica.datos_personales_url,
    )


@enrutador_pagos.get(
    "/pse/bancos",
    response_model=list[BancoPse],
    summary="Bancos de PSE",
    responses=respuestas_error(),
)
def bancos_pse(pasarela: Pasarela) -> list[BancoPse]:
    """Lista corta y acotada que da la pasarela (no se pagina). En sandbox, el banco `1`
    aprueba y el `2` rechaza.
    """
    return [BancoPse.model_validate(b) for b in pasarela.bancos_pse()]


@enrutador_pagos.get(
    "/devoluciones-pendientes",
    response_model=Pagina[PagoDetalle],
    summary="Devoluciones pendientes",
    responses=respuestas_error(401, 403, 422),
)
def devoluciones_pendientes(
    sesion: SesionBD, _: SoloAdministrador, parametros: Paginacion
) -> Pagina[PagoDetalle]:
    """Dinero que hay que devolver a un cliente: compras que no se completaron, alquileres
    cancelados con devolución, o pagos que se aprobaron cuando la reserva ya había expirado.
    """
    resultado = procesamiento.listar_devoluciones_pendientes(sesion, parametros)
    return Pagina[PagoDetalle].model_validate(resultado)


@enrutador_pagos.post(
    "/webhooks/wompi",
    response_model=EventoRecibido,
    summary="Eventos de Wompi (webhook)",
    responses=respuestas_error(413),
)
async def webhook_wompi(request: Request, sesion: SesionBD) -> EventoRecibido:
    """Lo llama Wompi, no el frontend. Verifica la firma, descarta repetidos y responde 200
    (si no, Wompi reintenta). El cuerpo crudo queda guardado.

    Un cuerpo de más de 64 KiB se rechaza con 413 sin leerlo entero ni guardarlo: un evento
    real de Wompi pesa unos pocos KiB.
    """
    cuerpo = await leer_cuerpo_limitado(request, LIMITE_CUERPO_WEBHOOK)
    secreto = obtener_configuracion().wompi_secreto_eventos
    procesamiento.procesar_evento_wompi(sesion, cuerpo, secreto)
    return EventoRecibido()


@enrutador_pagos.get(
    "/{referencia}",
    response_model=PagoDetalle,
    summary="Estado de un pago",
    responses=respuestas_error(401, 403, 404),
)
def ver(
    sesion: SesionBD, usuario: UsuarioActual, pasarela: Pasarela, referencia: str
) -> PagoDetalle:
    """Si el pago sigue `pendiente`, el backend le pregunta a la pasarela (consulta de
    respaldo) antes de responder. Consúltalo cada pocos segundos tras volver del banco.
    """
    pago = procesamiento.obtener_pago(sesion, referencia, usuario)
    return PagoDetalle.model_validate(procesamiento.sincronizar(sesion, pago, pasarela))


@enrutador_pagos.get(
    "/{referencia}/comprobante",
    summary="Comprobante de pago en PDF",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "El comprobante en PDF"},
        **respuestas_error(401, 403, 404),
    },
)
def comprobante(sesion: SesionBD, usuario: UsuarioActual, referencia: str) -> Response:
    """Valor, fecha, servicio, cliente y estado de la transacción (SRS 3.1.6)."""
    pago = procesamiento.obtener_pago(sesion, referencia, usuario)
    pdf = generar_pdf(datos_comprobante(sesion, pago))
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="comprobante-{referencia}.pdf"'},
    )


@enrutador_pagos.post(
    "/{referencia}/devolucion-ejecutada",
    response_model=PagoDetalle,
    summary="Marcar una devolución como hecha",
    responses=respuestas_error(401, 403, 404, 409, 422),
)
def devolucion_ejecutada(
    sesion: SesionBD, administrador: SoloAdministrador, referencia: str, datos: DevolucionEjecutada
) -> PagoDetalle:
    """El administrador hizo el reembolso en el panel de Wompi y lo registra aquí."""
    pago = procesamiento.marcar_devolucion_ejecutada(sesion, referencia, administrador, datos.nota)
    return PagoDetalle.model_validate(pago)
