"""Rutas de las ventas (HU-04).

Flujo del cliente: armar el carrito con ``/catalogo/modelos`` (vehículos) y
``/catalogo/productos`` (accesorios y repuestos) → comprar (``POST /ventas``) → pagar
dentro de 15 minutos (``/pago``) → descargar el comprobante preliminar (``/comprobante``).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.comun import fechas
from app.comun.errores import respuestas_error
from app.comun.paginacion import Pagina, Paginacion, ResultadoPagina
from app.db import SesionBD
from app.modulos.pagos.esquemas import PagoResumen
from app.modulos.pagos.pasarela import PasarelaPagos, obtener_pasarela
from app.modulos.usuarios.modelos import Rol, Usuario
from app.modulos.ventas import servicio
from app.modulos.ventas.esquemas import (
    CancelacionVenta,
    ComprobantePreliminar,
    PagoVentaCrear,
    PagoVentaRespuesta,
    VentaCrear,
    VentaRespuesta,
)
from app.modulos.ventas.modelos import EstadoVenta, Venta
from app.seguridad import AdministradorUOperador, SoloAdministrador, UsuarioActual, requiere_roles

enrutador_ventas = APIRouter(prefix="/ventas", tags=["ventas"])

SoloCliente = Annotated[Usuario, Depends(requiere_roles(Rol.CLIENTE))]
Pasarela = Annotated[PasarelaPagos, Depends(obtener_pasarela)]


def _respuesta(venta: Venta) -> VentaRespuesta:
    return VentaRespuesta.desde(venta, servicio.estado_vigente(venta, fechas.ahora()))


def _pagina(resultado: ResultadoPagina) -> Pagina[VentaRespuesta]:
    return Pagina[VentaRespuesta](
        elementos=[_respuesta(v) for v in resultado.elementos],
        total=resultado.total,
        pagina=resultado.pagina,
        tamano=resultado.tamano,
        paginas=resultado.paginas,
    )


@enrutador_ventas.post(
    "",
    response_model=VentaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Comprar",
    responses=respuestas_error(401, 403, 404, 409, 422),
)
def crear(sesion: SesionBD, cliente: SoloCliente, datos: VentaCrear) -> VentaRespuesta:
    """Compra vehículos (por modelo; el sistema asigna las unidades) y accesorios o repuestos.
    Las unidades quedan apartadas y el stock descontado **15 minutos** mientras el cliente
    paga (`expira_en`). Si no paga a tiempo, la compra expira y todo se devuelve.
    """
    return _respuesta(servicio.crear_venta(sesion, cliente, datos))


@enrutador_ventas.get(
    "/mias",
    response_model=Pagina[VentaRespuesta],
    summary="Mis compras",
    responses=respuestas_error(401, 403, 422),
)
def listar_mias(
    sesion: SesionBD,
    cliente: SoloCliente,
    parametros: Paginacion,
    estado: EstadoVenta | None = None,
) -> Pagina[VentaRespuesta]:
    """Las compras del cliente con sesión, de la más reciente a la más antigua."""
    return _pagina(servicio.listar_ventas(sesion, parametros, cliente_id=cliente.id, estado=estado))


@enrutador_ventas.get(
    "/devoluciones-pendientes",
    response_model=Pagina[VentaRespuesta],
    summary="Compras con devolución pendiente",
    responses=respuestas_error(401, 403, 422),
)
def listar_devoluciones_pendientes(
    sesion: SesionBD, _: SoloAdministrador, parametros: Paginacion
) -> Pagina[VentaRespuesta]:
    """Compras pagadas que no se pudieron completar porque una unidad entró en mantenimiento
    antes de aprobarse el pago. Hay que devolverle el dinero al cliente.
    """
    return _pagina(servicio.listar_devoluciones_pendientes(sesion, parametros))


@enrutador_ventas.get(
    "",
    response_model=Pagina[VentaRespuesta],
    summary="Todas las ventas",
    responses=respuestas_error(401, 403, 422),
)
def listar(
    sesion: SesionBD,
    _: AdministradorUOperador,
    parametros: Paginacion,
    estado: EstadoVenta | None = None,
    cliente_id: Annotated[int | None, Query(gt=0)] = None,
) -> Pagina[VentaRespuesta]:
    return _pagina(servicio.listar_ventas(sesion, parametros, cliente_id=cliente_id, estado=estado))


@enrutador_ventas.get(
    "/{venta_id}",
    response_model=VentaRespuesta,
    summary="Ver una compra",
    responses=respuestas_error(401, 403, 404),
)
def ver(sesion: SesionBD, usuario: UsuarioActual, venta_id: int) -> VentaRespuesta:
    """El cliente solo ve las suyas; el administrador y el operador, todas."""
    return _respuesta(servicio.obtener_venta(sesion, venta_id, usuario))


@enrutador_ventas.post(
    "/{venta_id}/pago",
    response_model=PagoVentaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Pagar una compra",
    responses=respuestas_error(401, 403, 404, 409, 422),
)
def pagar(
    sesion: SesionBD,
    cliente: SoloCliente,
    pasarela: Pasarela,
    venta_id: int,
    datos: PagoVentaCrear,
) -> PagoVentaRespuesta:
    """Cobra el `total` de una compra en `pendiente_pago`. Revisa `pago.estado` y `venta.estado`:

    - `aprobado` y venta `pagada`: compra completa; las unidades quedan vendidas.
    - `aprobado` y venta `cancelada`: una unidad entró en mantenimiento antes del pago; la
      compra no se completa y `devolucion` trae la devolución del dinero.
    - `rechazado`: la compra sigue pendiente; se puede reintentar antes de `expira_en`.

    En desarrollo la pasarela es **falsa**: aprueba al instante y no mueve dinero.
    """
    resultado = servicio.pagar_venta(sesion, venta_id, cliente, datos.metodo_pago, pasarela)
    return PagoVentaRespuesta(
        venta=_respuesta(resultado.venta),
        pago=PagoResumen.model_validate(resultado.pago),
        devolucion=PagoResumen.model_validate(resultado.devolucion)
        if resultado.devolucion
        else None,
    )


@enrutador_ventas.post(
    "/{venta_id}/cancelacion",
    response_model=VentaRespuesta,
    summary="Cancelar una compra sin pagar",
    responses=respuestas_error(401, 403, 404, 409, 422),
)
def cancelar(
    sesion: SesionBD, cliente: SoloCliente, venta_id: int, datos: CancelacionVenta
) -> VentaRespuesta:
    """Solo mientras está en `pendiente_pago`. Devuelve el stock y suelta las unidades."""
    return _respuesta(servicio.cancelar_venta(sesion, venta_id, cliente, datos.motivo))


@enrutador_ventas.get(
    "/{venta_id}/comprobante",
    response_model=ComprobantePreliminar,
    summary="Comprobante preliminar",
    responses=respuestas_error(401, 403, 404),
)
def comprobante(sesion: SesionBD, usuario: UsuarioActual, venta_id: int) -> ComprobantePreliminar:
    """Resumen de la compra con cliente, ítems, total, estado y pago. **No es una factura**:
    el comprobante definitivo en PDF llega con HU-05.
    """
    datos = servicio.obtener_comprobante(sesion, venta_id, usuario)
    ahora = fechas.ahora()
    return ComprobantePreliminar.desde(
        datos.venta, servicio.estado_vigente(datos.venta, ahora), datos.pago, datos.metodo, ahora
    )
