"""Rutas de los domicilios (HU-06, HU-07).

Flujo: el cliente marca el punto en el mapa (``/domicilios/cobertura`` le dice la zona y
la tarifa) → agrega el domicilio a su reserva o compra antes de pagar
(``POST /domicilios``) → paga el total con el envío → el despacho asigna un domiciliario
(``/asignacion``) → el domiciliario avanza el estado (``/estado``) → cualquiera con el
código sigue el pedido (``/domicilios/rastreo/{codigo}``).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.comun.errores import respuestas_error
from app.comun.paginacion import Pagina, Paginacion, ResultadoPagina
from app.db import SesionBD
from app.modulos.domicilios import servicio
from app.modulos.domicilios.esquemas import (
    AsignacionCrear,
    CambioDeEstado,
    CancelacionDomicilioRespuesta,
    CancelacionPorDespacho,
    Cobertura,
    DomicilioCrear,
    DomicilioRespuesta,
    Latitud,
    Longitud,
    PersonaContacto,
    RastreoPublico,
    ZonaRespuesta,
)
from app.modulos.domicilios.modelos import EstadoDomicilio
from app.modulos.pagos.esquemas import PagoResumen
from app.modulos.usuarios.modelos import Rol, Usuario
from app.seguridad import AdministradorUOperador, UsuarioActual, requiere_roles

enrutador_domicilios = APIRouter(prefix="/domicilios", tags=["domicilios"])

SoloCliente = Annotated[Usuario, Depends(requiere_roles(Rol.CLIENTE))]
SoloDomiciliario = Annotated[Usuario, Depends(requiere_roles(Rol.DOMICILIARIO))]


def _respuesta(datos: servicio.DomicilioConTotales) -> DomicilioRespuesta:
    return DomicilioRespuesta.desde(datos.domicilio, datos.valor_envio, datos.total)


def _pagina(resultado: ResultadoPagina) -> Pagina[DomicilioRespuesta]:
    return Pagina[DomicilioRespuesta](
        elementos=[_respuesta(d) for d in resultado.elementos],
        total=resultado.total,
        pagina=resultado.pagina,
        tamano=resultado.tamano,
        paginas=resultado.paginas,
    )


@enrutador_domicilios.get(
    "/zonas",
    response_model=Pagina[ZonaRespuesta],
    summary="Zonas de cobertura",
    responses=respuestas_error(422),
)
def listar_zonas(sesion: SesionBD, parametros: Paginacion) -> Pagina[ZonaRespuesta]:
    """Polígonos GeoJSON y tarifa de envío de cada zona activa, para dibujarlos en el mapa."""
    return Pagina[ZonaRespuesta].model_validate(servicio.listar_zonas(sesion, parametros))


@enrutador_domicilios.get(
    "/cobertura",
    response_model=Cobertura,
    summary="¿Llegamos a este punto?",
    responses=respuestas_error(422),
)
def cobertura(
    sesion: SesionBD,
    latitud: Annotated[Latitud, Query()],
    longitud: Annotated[Longitud, Query()],
) -> Cobertura:
    """La zona y la tarifa de envío del punto marcado en el mapa. Fuera de cobertura
    responde 422 con `fuera_de_cobertura`.
    """
    zona = servicio.zona_para_punto(sesion, latitud, longitud)
    return Cobertura(zona_id=zona.id, zona=zona.nombre, tarifa_envio=zona.tarifa_envio)


@enrutador_domicilios.get(
    "/rastreo/{codigo}",
    response_model=RastreoPublico,
    summary="Seguir un pedido por su código",
    responses=respuestas_error(404),
)
def rastreo(sesion: SesionBD, codigo: str) -> RastreoPublico:
    """Público, sin iniciar sesión (SRS 3.6.4): el estado actual y la hora de cada cambio.
    No muestra dirección ni datos personales. El código no distingue mayúsculas.
    """
    return RastreoPublico.model_validate(servicio.rastreo_publico(sesion, codigo))


@enrutador_domicilios.post(
    "",
    response_model=DomicilioRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Solicitar domicilio para una reserva o compra",
    responses=respuestas_error(401, 403, 404, 409, 422),
)
def solicitar(sesion: SesionBD, cliente: SoloCliente, datos: DomicilioCrear) -> DomicilioRespuesta:
    """Solo antes de pagar (`pendiente_pago`). La tarifa de la zona se suma al total de la
    operación (`total_operacion`), que es lo que se paga después.
    """
    resultado = servicio.solicitar_domicilio(
        sesion,
        cliente,
        alquiler_id=datos.alquiler_id,
        venta_id=datos.venta_id,
        direccion=datos.direccion,
        indicaciones=datos.indicaciones,
        latitud=datos.latitud,
        longitud=datos.longitud,
    )
    return _respuesta(resultado)


@enrutador_domicilios.get(
    "/mios",
    response_model=Pagina[DomicilioRespuesta],
    summary="Mis domicilios",
    responses=respuestas_error(401, 403, 422),
)
def listar_mios(
    sesion: SesionBD, cliente: SoloCliente, parametros: Paginacion
) -> Pagina[DomicilioRespuesta]:
    return _pagina(servicio.listar_domicilios(sesion, parametros, cliente_id=cliente.id))


@enrutador_domicilios.get(
    "/asignados",
    response_model=Pagina[DomicilioRespuesta],
    summary="Mis entregas (domiciliario)",
    responses=respuestas_error(401, 403, 422),
)
def listar_asignados(
    sesion: SesionBD, domiciliario: SoloDomiciliario, parametros: Paginacion
) -> Pagina[DomicilioRespuesta]:
    """Las entregas en ruta del domiciliario, con la dirección, el contacto del cliente y el
    `vehiculo_transporte` que usa: es el único vehículo sobre el que puede reportar novedades.
    """
    resultado = servicio.listar_domicilios(
        sesion, parametros, domiciliario_id=domiciliario.id, solo_en_ruta=True
    )
    return _pagina(resultado)


@enrutador_domicilios.get(
    "/domiciliarios-disponibles",
    response_model=Pagina[PersonaContacto],
    summary="Domiciliarios disponibles",
    responses=respuestas_error(401, 403, 422),
)
def domiciliarios_disponibles(
    sesion: SesionBD, _: AdministradorUOperador, parametros: Paginacion
) -> Pagina[PersonaContacto]:
    """Domiciliarios activos sin entregas en ruta: los que se pueden asignar ahora."""
    resultado = servicio.listar_domiciliarios_disponibles(sesion, parametros)
    return Pagina[PersonaContacto].model_validate(resultado)


@enrutador_domicilios.get(
    "",
    response_model=Pagina[DomicilioRespuesta],
    summary="Todos los domicilios",
    responses=respuestas_error(401, 403, 422),
)
def listar(
    sesion: SesionBD,
    _: AdministradorUOperador,
    parametros: Paginacion,
    estado: EstadoDomicilio | None = None,
) -> Pagina[DomicilioRespuesta]:
    """Para el despacho: con `estado=pendiente`, los que esperan domiciliario."""
    return _pagina(servicio.listar_domicilios(sesion, parametros, estado=estado))


@enrutador_domicilios.get(
    "/{domicilio_id}",
    response_model=DomicilioRespuesta,
    summary="Ver un domicilio",
    responses=respuestas_error(401, 403, 404),
)
def ver(sesion: SesionBD, usuario: UsuarioActual, domicilio_id: int) -> DomicilioRespuesta:
    """El cliente ve los suyos; el domiciliario, los que tiene asignados; el despacho, todos."""
    return _respuesta(servicio.obtener_domicilio(sesion, domicilio_id, usuario))


@enrutador_domicilios.post(
    "/{domicilio_id}/cancelacion",
    response_model=DomicilioRespuesta,
    summary="Quitar el domicilio antes de pagar",
    responses=respuestas_error(401, 403, 404, 409),
)
def cancelar(sesion: SesionBD, cliente: SoloCliente, domicilio_id: int) -> DomicilioRespuesta:
    """El envío sale del total. Para cambiar la dirección: quitar y solicitar de nuevo."""
    return _respuesta(servicio.cancelar_domicilio(sesion, domicilio_id, cliente))


@enrutador_domicilios.post(
    "/{domicilio_id}/asignacion",
    response_model=DomicilioRespuesta,
    summary="Asignar el domiciliario",
    responses=respuestas_error(401, 403, 404, 409, 422),
)
def asignar(
    sesion: SesionBD, usuario: AdministradorUOperador, domicilio_id: int, datos: AsignacionCrear
) -> DomicilioRespuesta:
    """`pendiente` → `asignado`. Solo con la operación pagada y un domiciliario disponible.
    El vehículo de transporte es opcional.
    """
    resultado = servicio.asignar_domiciliario(
        sesion, domicilio_id, usuario, datos.domiciliario_id, datos.vehiculo_transporte_id
    )
    return _respuesta(resultado)


@enrutador_domicilios.post(
    "/{domicilio_id}/estado",
    response_model=DomicilioRespuesta,
    summary="Avanzar el estado de la entrega",
    responses=respuestas_error(401, 403, 404, 409, 422),
)
def avanzar_estado(
    sesion: SesionBD, usuario: UsuarioActual, domicilio_id: int, datos: CambioDeEstado
) -> DomicilioRespuesta:
    """El domiciliario asignado (o el administrador u operador, para corregir) marca
    `recogido`, `en_camino` o `entregado`, sin saltar pasos. Al entregar un alquiler, este
    pasa a `en_curso` (igual que la entrega en el local) y el vehículo de transporte vuelve a
    la flota. Al entregar queda el **acta de entrega** (HU-11).
    """
    estado = EstadoDomicilio(datos.estado)
    acta = datos.acta.datos() if datos.acta else None
    return _respuesta(servicio.avanzar_estado(sesion, domicilio_id, usuario, estado, acta))


@enrutador_domicilios.post(
    "/{domicilio_id}/cancelacion-por-despacho",
    response_model=CancelacionDomicilioRespuesta,
    summary="Cancelar una entrega pagada",
    responses=respuestas_error(401, 403, 404, 409, 422),
)
def cancelar_por_despacho(
    sesion: SesionBD,
    usuario: AdministradorUOperador,
    domicilio_id: int,
    datos: CancelacionPorDespacho,
) -> CancelacionDomicilioRespuesta:
    """Para entregas pagadas, asignadas o en ruta. Registra la devolución del envío
    (`devolucion`); la reserva o la compra sigue vigente y se recoge en el local.
    """
    resultado = servicio.cancelar_por_despacho(sesion, domicilio_id, usuario, datos.motivo)
    return CancelacionDomicilioRespuesta(
        domicilio=_respuesta(resultado.entrega),
        devolucion=PagoResumen.model_validate(resultado.devolucion)
        if resultado.devolucion
        else None,
    )
