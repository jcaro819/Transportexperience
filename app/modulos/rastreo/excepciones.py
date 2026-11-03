"""Errores de negocio del rastreo GPS (HU-08). Cada uno dice la causa y qué hacer."""

from fastapi import status

from app.comun.errores import ErrorDeNegocio


class ClaveGpsInvalida(ErrorDeNegocio):
    codigo = "clave_gps_invalida"
    mensaje = "La clave del dispositivo GPS falta o no es válida."
    accion = "Envía la clave del vehículo en el encabezado X-Clave-Gps. Si se perdió, emite otra."
    estado_http = status.HTTP_401_UNAUTHORIZED


class FuenteGpsDesactivada(ErrorDeNegocio):
    codigo = "fuente_gps_desactivada"
    mensaje = "El sistema no está recibiendo posiciones de esta fuente (simulador o dispositivo)."
    accion = "Revisa GPS_FUENTE en el .env del servidor, o emite la clave con la fuente correcta."
    estado_http = status.HTTP_403_FORBIDDEN


class PosicionFueraDeTiempo(ErrorDeNegocio):
    codigo = "posicion_fuera_de_tiempo"
    mensaje = "La hora de la posición está en el futuro o es demasiado vieja."
    accion = "Revisa el reloj del dispositivo; las posiciones de más de 7 días no se guardan."
    estado_http = status.HTTP_422_UNPROCESSABLE_CONTENT


class RangoDeRecorridoInvalido(ErrorDeNegocio):
    codigo = "rango_de_recorrido_invalido"
    mensaje = "El rango de fechas del recorrido no es válido."
    accion = "Usa un `desde` anterior al `hasta`, dentro de los últimos 7 días."
    estado_http = status.HTTP_422_UNPROCESSABLE_CONTENT
