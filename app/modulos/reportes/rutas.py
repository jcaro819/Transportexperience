"""Rutas de las actas de entrega y recepción (HU-11).

Las actas no se crean aquí: nacen solas al entregar o recibir un vehículo (en el local y
por domicilio). Aquí se consultan, se descargan en PDF, se exportan a Excel o PDF y el
cliente da su conformidad.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.comun.errores import respuestas_error
from app.comun.paginacion import Pagina, Paginacion, ResultadoPagina
from app.db import SesionBD
from app.modulos.reportes import servicio
from app.modulos.reportes.documentos import cliente, excel_reporte, pdf_reporte
from app.modulos.reportes.esquemas import ActaRespuesta, Conformidad, VerificacionActa
from app.modulos.reportes.modelos import Acta, TipoActa
from app.modulos.usuarios.modelos import Rol, Usuario
from app.seguridad import AdministradorUOperador, UsuarioActual, requiere_roles

enrutador_actas = APIRouter(prefix="/actas", tags=["actas"])

SoloCliente = Annotated[Usuario, Depends(requiere_roles(Rol.CLIENTE))]
_PDF = {200: {"content": {"application/pdf": {}}, "description": "El documento en PDF"}}
_EXCEL_TIPO = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_EXCEL = {200: {"content": {_EXCEL_TIPO: {}}, "description": "El reporte en Excel"}}


def _respuesta(acta: Acta) -> ActaRespuesta:
    del_cliente = cliente(acta)
    return ActaRespuesta(
        id=acta.id,
        numero=acta.numero,
        tipo=acta.tipo,
        creado_en=acta.creado_en,
        vehiculo_id=acta.vehiculo_id,
        vehiculo_codigo=acta.vehiculo.codigo,
        modelo=acta.vehiculo.modelo.nombre,
        alquiler_id=acta.alquiler_id,
        venta_id=acta.venta_id,
        domicilio_id=acta.domicilio_id,
        cliente_id=del_cliente.id,
        cliente=del_cliente.nombre_completo,
        estado_vehiculo=acta.estado_vehiculo,
        nivel_bateria=acta.nivel_bateria,
        registrada_por=acta.registrada_por.nombre_completo,
        conformidad=Conformidad(
            conforme_por_id=acta.conforme_por_id,
            conforme_por=acta.conforme_por.nombre_completo,
            conforme_en=acta.conforme_en,
            hash_pdf=acta.hash_pdf,
        )
        if acta.conforme_en
        else None,
    )


def _pagina(resultado: ResultadoPagina) -> Pagina[ActaRespuesta]:
    return Pagina[ActaRespuesta](
        elementos=[_respuesta(a) for a in resultado.elementos],
        total=resultado.total,
        pagina=resultado.pagina,
        tamano=resultado.tamano,
        paginas=resultado.paginas,
    )


def _archivo(contenido: bytes, tipo: str, nombre: str) -> Response:
    return Response(
        contenido,
        media_type=tipo,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


Desde = Annotated[date | None, Query(description="Primer día (AAAA-MM-DD).")]
Hasta = Annotated[date | None, Query(description="Último día, inclusive.")]


@enrutador_actas.get(
    "",
    response_model=Pagina[ActaRespuesta],
    summary="Actas",
    responses=respuestas_error(401, 403, 422),
)
def listar(
    sesion: SesionBD,
    usuario: AdministradorUOperador,
    parametros: Paginacion,
    tipo: TipoActa | None = None,
    vehiculo_id: Annotated[int | None, Query(gt=0)] = None,
    desde: Desde = None,
    hasta: Hasta = None,
) -> Pagina[ActaRespuesta]:
    """Todas las actas, de la más reciente a la más antigua."""
    resultado = servicio.listar_actas(
        sesion, parametros, usuario, tipo=tipo, vehiculo_id=vehiculo_id, desde=desde, hasta=hasta
    )
    return _pagina(resultado)


@enrutador_actas.get(
    "/mias",
    response_model=Pagina[ActaRespuesta],
    summary="Mis actas",
    responses=respuestas_error(401, 403, 422),
)
def listar_mias(
    sesion: SesionBD, cliente: SoloCliente, parametros: Paginacion
) -> Pagina[ActaRespuesta]:
    """Las actas de los alquileres y compras del cliente con sesión."""
    return _pagina(servicio.listar_actas(sesion, parametros, cliente))


@enrutador_actas.get(
    "/exportacion/excel",
    summary="Exportar actas a Excel",
    response_class=Response,
    responses={**_EXCEL, **respuestas_error(401, 403, 422)},
)
def exportar_excel(
    sesion: SesionBD,
    usuario: AdministradorUOperador,
    desde: Desde = None,
    hasta: Hasta = None,
    tipo: TipoActa | None = None,
) -> Response:
    """Una fila por acta del rango (por defecto, los últimos 30 días; máximo 92)."""
    datos = servicio.reporte(sesion, usuario, desde=desde, hasta=hasta, tipo=tipo)
    return _archivo(excel_reporte(datos.actas, datos.titulo), _EXCEL_TIPO, "actas.xlsx")


@enrutador_actas.get(
    "/exportacion/pdf",
    summary="Exportar actas a PDF",
    response_class=Response,
    responses={**_PDF, **respuestas_error(401, 403, 422)},
)
def exportar_pdf(
    sesion: SesionBD,
    usuario: AdministradorUOperador,
    desde: Desde = None,
    hasta: Hasta = None,
    tipo: TipoActa | None = None,
) -> Response:
    """Las actas del rango en una tabla (por defecto, los últimos 30 días; máximo 92)."""
    datos = servicio.reporte(sesion, usuario, desde=desde, hasta=hasta, tipo=tipo)
    return _archivo(pdf_reporte(datos.actas, datos.titulo), "application/pdf", "actas.pdf")


@enrutador_actas.get(
    "/{acta_id}",
    response_model=ActaRespuesta,
    summary="Ver un acta",
    responses=respuestas_error(401, 403, 404),
)
def ver(sesion: SesionBD, usuario: UsuarioActual, acta_id: int) -> ActaRespuesta:
    """El cliente ve las suyas; el administrador y el operador, todas."""
    return _respuesta(servicio.obtener_acta(sesion, acta_id, usuario))


@enrutador_actas.get(
    "/{acta_id}/pdf",
    summary="Acta en PDF",
    response_class=Response,
    responses={**_PDF, **respuestas_error(401, 403, 404)},
)
def descargar_pdf(sesion: SesionBD, usuario: UsuarioActual, acta_id: int) -> Response:
    """Siempre el mismo PDF para la misma acta: su SHA-256 es la huella de la conformidad."""
    contenido = servicio.pdf(sesion, acta_id, usuario)
    return _archivo(contenido, "application/pdf", f"acta-{acta_id:06d}.pdf")


@enrutador_actas.post(
    "/{acta_id}/conformidad",
    response_model=ActaRespuesta,
    summary="Dar la conformidad (cliente)",
    responses=respuestas_error(401, 403, 404, 409),
)
def dar_conformidad(sesion: SesionBD, usuario: UsuarioActual, acta_id: int) -> ActaRespuesta:
    """El cliente de la operación acepta el acta tal como está en su PDF. Queda su usuario, la
    fecha y el SHA-256 del PDF. Solo una vez. *(Mecanismo pendiente de confirmación del equipo.)*
    """
    return _respuesta(servicio.dar_conformidad(sesion, acta_id, usuario))


@enrutador_actas.get(
    "/{acta_id}/verificacion",
    response_model=VerificacionActa,
    summary="¿El PDF sigue siendo el que se aceptó?",
    responses=respuestas_error(401, 403, 404),
)
def verificar(sesion: SesionBD, usuario: UsuarioActual, acta_id: int) -> VerificacionActa:
    """Regenera el PDF y compara su SHA-256 con el guardado en la conformidad."""
    coincide = servicio.verificar(sesion, acta_id, usuario)
    acta = servicio.obtener_acta(sesion, acta_id, usuario)
    return VerificacionActa(
        con_conformidad=coincide is not None, coincide=coincide, hash_pdf=acta.hash_pdf
    )
