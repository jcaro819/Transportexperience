"""Rutas de los alquileres (HU-03).

Flujo del cliente: reservar (``POST /alquileres``) → pagar dentro de 15 minutos
(``/pago``) → el operador entrega (``/entrega``) → el operador recibe (``/devolucion``).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.comun import fechas
from app.comun.errores import respuestas_error
from app.comun.paginacion import Pagina, Paginacion, ResultadoPagina
from app.db import SesionBD
from app.modulos.alquileres import servicio
from app.modulos.alquileres.esquemas import (
    AlquilerCrear,
    AlquilerRespuesta,
    CancelacionAlquiler,
    PagoAlquilerCrear,
    PagoAlquilerRespuesta,
    PagoResumen,
    ReasignacionAlquiler,
)
from app.modulos.alquileres.modelos import Alquiler, EstadoAlquiler
from app.modulos.pagos.pasarela import PasarelaPagos, obtener_pasarela
from app.modulos.usuarios.modelos import Rol, Usuario
from app.seguridad import AdministradorUOperador, SoloAdministrador, UsuarioActual, requiere_roles

enrutador_alquileres = APIRouter(prefix="/alquileres", tags=["alquileres"])

SoloCliente = Annotated[Usuario, Depends(requiere_roles(Rol.CLIENTE))]
Pasarela = Annotated[PasarelaPagos, Depends(obtener_pasarela)]


def _respuesta(alquiler: Alquiler) -> AlquilerRespuesta:
    return AlquilerRespuesta.desde(alquiler, servicio.estado_vigente(alquiler, fechas.ahora()))


def _pagina(resultado: ResultadoPagina) -> Pagina[AlquilerRespuesta]:
    return Pagina[AlquilerRespuesta](
        elementos=[_respuesta(a) for a in resultado.elementos],
        total=resultado.total,
        pagina=resultado.pagina,
        tamano=resultado.tamano,
        paginas=resultado.paginas,
    )


@enrutador_alquileres.post(
    "",
    response_model=AlquilerRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Reservar un vehículo",
    responses=respuestas_error(401, 403, 404, 409, 422),
)
def crear(sesion: SesionBD, cliente: SoloCliente, datos: AlquilerCrear) -> AlquilerRespuesta:
    """Reserva una unidad libre del modelo en esas fechas y la guarda **15 minutos** mientras
    el cliente paga (`expira_en`). Si no paga a tiempo, la reserva expira y la unidad se
    libera sola. El precio es la tarifa diaria por los días, contando inicio y fin.
    """
    alquiler = servicio.crear_alquiler(
        sesion, cliente, datos.modelo_id, datos.fecha_inicio, datos.fecha_fin
    )
    return _respuesta(alquiler)


@enrutador_alquileres.get(
    "/mios",
    response_model=Pagina[AlquilerRespuesta],
    summary="Mis alquileres",
    responses=respuestas_error(401, 403, 422),
)
def listar_mios(
    sesion: SesionBD,
    cliente: SoloCliente,
    parametros: Paginacion,
    estado: EstadoAlquiler | None = None,
) -> Pagina[AlquilerRespuesta]:
    """Los alquileres del cliente con sesión, del más reciente al más antiguo."""
    resultado = servicio.listar_alquileres(sesion, parametros, cliente_id=cliente.id, estado=estado)
    return _pagina(resultado)


@enrutador_alquileres.get(
    "/en-riesgo",
    response_model=Pagina[AlquilerRespuesta],
    summary="Alquileres en riesgo",
    responses=respuestas_error(401, 403, 422),
)
def listar_en_riesgo(
    sesion: SesionBD, _: AdministradorUOperador, parametros: Paginacion
) -> Pagina[AlquilerRespuesta]:
    """Alquileres aún no entregados cuya unidad está en mantenimiento: hay que reasignarlos,
    esperar a que la unidad vuelva o cancelarlos con devolución.
    """
    return _pagina(servicio.listar_en_riesgo(sesion, parametros))


@enrutador_alquileres.get(
    "",
    response_model=Pagina[AlquilerRespuesta],
    summary="Todos los alquileres",
    responses=respuestas_error(401, 403, 422),
)
def listar(
    sesion: SesionBD,
    _: AdministradorUOperador,
    parametros: Paginacion,
    estado: EstadoAlquiler | None = None,
    vehiculo_id: Annotated[int | None, Query(gt=0)] = None,
    cliente_id: Annotated[int | None, Query(gt=0)] = None,
) -> Pagina[AlquilerRespuesta]:
    """Para el mostrador: buscar el alquiler que se va a entregar o recibir."""
    resultado = servicio.listar_alquileres(
        sesion, parametros, cliente_id=cliente_id, vehiculo_id=vehiculo_id, estado=estado
    )
    return _pagina(resultado)


@enrutador_alquileres.get(
    "/{alquiler_id}",
    response_model=AlquilerRespuesta,
    summary="Ver un alquiler",
    responses=respuestas_error(401, 403, 404),
)
def ver(sesion: SesionBD, usuario: UsuarioActual, alquiler_id: int) -> AlquilerRespuesta:
    """El cliente solo ve los suyos; el administrador y el operador, todos."""
    return _respuesta(servicio.obtener_alquiler(sesion, alquiler_id, usuario))


@enrutador_alquileres.post(
    "/{alquiler_id}/pago",
    response_model=PagoAlquilerRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Pagar una reserva",
    responses=respuestas_error(401, 403, 404, 409, 422),
)
def pagar(
    sesion: SesionBD,
    cliente: SoloCliente,
    pasarela: Pasarela,
    alquiler_id: int,
    datos: PagoAlquilerCrear,
) -> PagoAlquilerRespuesta:
    """Cobra el `total` de una reserva en `pendiente_pago`. Revisa `pago.estado`:

    - `aprobado`: el alquiler pasa a `confirmado`.
    - `rechazado`: el alquiler sigue pendiente; se puede reintentar antes de `expira_en`.
    - `pendiente`: (desde HU-05, con PSE) la confirmación llega después; consulta el alquiler.

    En desarrollo la pasarela es **falsa**: aprueba al instante y no mueve dinero.
    """
    resultado = servicio.pagar_alquiler(sesion, alquiler_id, cliente, datos.metodo_pago, pasarela)
    return PagoAlquilerRespuesta(
        alquiler=_respuesta(resultado.alquiler),
        pago=PagoResumen.model_validate(resultado.pago),
    )


@enrutador_alquileres.post(
    "/{alquiler_id}/cancelacion",
    response_model=AlquilerRespuesta,
    summary="Cancelar una reserva sin pagar",
    responses=respuestas_error(401, 403, 404, 409, 422),
)
def cancelar(
    sesion: SesionBD, cliente: SoloCliente, alquiler_id: int, datos: CancelacionAlquiler
) -> AlquilerRespuesta:
    """Solo mientras está en `pendiente_pago`. Un alquiler pagado no se cancela desde aquí."""
    return _respuesta(servicio.cancelar_alquiler(sesion, alquiler_id, cliente, datos.motivo))


@enrutador_alquileres.post(
    "/{alquiler_id}/entrega",
    response_model=AlquilerRespuesta,
    summary="Entregar el vehículo al cliente",
    responses=respuestas_error(401, 403, 404, 409),
)
def entregar(
    sesion: SesionBD, usuario: AdministradorUOperador, alquiler_id: int
) -> AlquilerRespuesta:
    """`confirmado` → `en_curso`, y la unidad pasa a `alquilado`. Solo entre la fecha de
    inicio y la de fin, y si la unidad está disponible (si está en mantenimiento, reasigna).
    """
    return _respuesta(servicio.entregar_vehiculo(sesion, alquiler_id, usuario))


@enrutador_alquileres.post(
    "/{alquiler_id}/devolucion",
    response_model=AlquilerRespuesta,
    summary="Recibir el vehículo de vuelta",
    responses=respuestas_error(401, 403, 404, 409),
)
def recibir(
    sesion: SesionBD, usuario: AdministradorUOperador, alquiler_id: int
) -> AlquilerRespuesta:
    """`en_curso` → `finalizado`, y la unidad vuelve a `disponible`. Si entró en
    mantenimiento durante el alquiler, se queda en mantenimiento hasta que el taller cierre
    su novedad.
    """
    return _respuesta(servicio.recibir_vehiculo(sesion, alquiler_id, usuario))


@enrutador_alquileres.post(
    "/{alquiler_id}/reasignacion",
    response_model=AlquilerRespuesta,
    summary="Mover el alquiler a otra unidad",
    responses=respuestas_error(401, 403, 404, 409, 422),
)
def reasignar(
    sesion: SesionBD, usuario: SoloAdministrador, alquiler_id: int, datos: ReasignacionAlquiler
) -> AlquilerRespuesta:
    """Mueve un alquiler aún no entregado a otra unidad libre del **mismo modelo**, con las
    mismas fechas y el mismo precio. Pensado para los alquileres en riesgo.
    """
    alquiler = servicio.reasignar_alquiler(sesion, alquiler_id, usuario, datos.vehiculo_id)
    return _respuesta(alquiler)
