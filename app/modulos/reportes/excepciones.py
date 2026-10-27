"""Errores de negocio de los reportes y las actas (HU-11). Cada uno dice la causa y qué hacer."""

from fastapi import status

from app.comun.errores import ErrorDeNegocio


class ActaNoEncontrada(ErrorDeNegocio):
    codigo = "acta_no_encontrada"
    mensaje = "No encontramos esa acta."
    accion = "Revisa la lista de actas."
    estado_http = status.HTTP_404_NOT_FOUND


class ConformidadYaRegistrada(ErrorDeNegocio):
    codigo = "conformidad_ya_registrada"
    mensaje = "Esta acta ya tiene la conformidad registrada."
    accion = "No hace falta volver a darla: consulta el acta para ver quién y cuándo la dio."
    estado_http = status.HTTP_409_CONFLICT


class RangoDeReporteInvalido(ErrorDeNegocio):
    codigo = "rango_de_reporte_invalido"
    mensaje = "El rango de fechas del reporte no es válido."
    accion = "Usa un `desde` anterior o igual al `hasta`, con un máximo de 92 días."
    estado_http = status.HTTP_422_UNPROCESSABLE_CONTENT
