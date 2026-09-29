"""Errores de negocio del módulo de usuarios. Cada uno dice la causa y qué hacer (SRS 3.2.3)."""

from fastapi import status

from app.comun.errores import ErrorDeNegocio


class CorreoYaRegistrado(ErrorDeNegocio):
    codigo = "correo_ya_registrado"
    mensaje = "Ya existe una cuenta con ese correo."
    accion = "Inicia sesión o usa otro correo."
    estado_http = status.HTTP_409_CONFLICT


class CredencialesInvalidas(ErrorDeNegocio):
    # Mismo mensaje si el correo no existe o si la contraseña está mal: no se revela cuál.
    codigo = "credenciales_invalidas"
    mensaje = "El correo o la contraseña no son correctos."
    accion = "Revisa los datos e inténtalo de nuevo."
    estado_http = status.HTTP_401_UNAUTHORIZED
    encabezados = {"WWW-Authenticate": "Bearer"}


class CuentaInactiva(ErrorDeNegocio):
    codigo = "cuenta_inactiva"
    mensaje = "Tu cuenta está desactivada."
    accion = "Comunícate con un administrador para reactivarla."
    estado_http = status.HTTP_403_FORBIDDEN


class UsuarioNoEncontrado(ErrorDeNegocio):
    codigo = "usuario_no_encontrado"
    mensaje = "No existe un usuario con ese identificador."
    accion = "Verifica el identificador o busca el usuario en la lista."
    estado_http = status.HTTP_404_NOT_FOUND


class CambioSobreSiMismo(ErrorDeNegocio):
    codigo = "cambio_sobre_si_mismo"
    mensaje = "No puedes desactivar tu propia cuenta ni quitarte el rol de administrador."
    accion = "Pide a otro administrador que haga el cambio."
    estado_http = status.HTTP_409_CONFLICT
