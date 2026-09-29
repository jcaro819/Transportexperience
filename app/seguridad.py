"""Seguridad: hash de contraseñas, tokens JWT y dependencias de permisos por rol (HU-12).

Autenticación: flujo OAuth2 con contraseña de FastAPI, que emite un JWT (contradicción 8
del CLAUDE.md). El token viaja en ``Authorization: Bearer <token>``.

Para proteger una ruta::

    @enrutador.get("/algo")
    def algo(usuario: UsuarioActual): ...                  # cualquier usuario con sesión

    @enrutador.get("/admin")
    def admin(usuario: SoloAdministrador): ...             # solo administradores

    @enrutador.get("/flota")
    def flota(usuario: Annotated[Usuario, Depends(requiere_roles(Rol.ADMINISTRADOR,
                                                                 Rol.OPERADOR))]): ...
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext

from app.comun.errores import NoAutenticado, PermisoDenegado, SesionExpirada
from app.config import obtener_configuracion
from app.db import SesionBD
from app.modulos.usuarios.modelos import Rol, Usuario

# passlib 1.7.4 intenta leer bcrypt.__about__, que bcrypt 4.1+ ya no tiene. Lo registra
# como error aunque el hash funciona bien; se silencia para no ensuciar la salida.
logging.getLogger("passlib.handlers.bcrypt").setLevel(logging.ERROR)

ALGORITMO_JWT = "HS256"

# bcrypt es lento a propósito (12 rondas ≈ 0,25 s). En los tests se bajan a 4 rondas
# para que la suite no tarde; el algoritmo es el mismo.
_RONDAS_BCRYPT = 4 if obtener_configuracion().entorno == "pruebas" else 12
_contexto = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=_RONDAS_BCRYPT)

# auto_error=False: si falta el token, respondemos con el error uniforme de la API.
_esquema_oauth2 = OAuth2PasswordBearer(tokenUrl="/autenticacion/token", auto_error=False)


def hashear_contrasena(contrasena: str) -> str:
    """Devuelve el hash bcrypt de ``contrasena``. Nunca se guarda la contraseña en claro."""
    return _contexto.hash(contrasena)


def verificar_contrasena(contrasena: str, hash_guardado: str) -> bool:
    """Indica si ``contrasena`` corresponde a ``hash_guardado``."""
    return _contexto.verify(contrasena, hash_guardado)


def crear_token_acceso(usuario: Usuario, ahora: datetime | None = None) -> tuple[str, int]:
    """Emite un JWT para ``usuario``. Devuelve el token y su duración en segundos."""
    config = obtener_configuracion()
    ahora = ahora or datetime.now(UTC)
    duracion = timedelta(minutes=config.jwt_minutos_expiracion)
    datos = {
        "sub": str(usuario.id),
        "rol": usuario.rol.value,
        "iat": ahora,
        "exp": ahora + duracion,
    }
    token = jwt.encode(datos, config.jwt_secreto, algorithm=ALGORITMO_JWT)
    return token, int(duracion.total_seconds())


def leer_token(token: str) -> int:
    """Valida firma y vencimiento del token y devuelve el id del usuario.

    Lanza ``SesionExpirada`` si venció y ``NoAutenticado`` si es inválido o fue alterado.
    """
    try:
        datos = jwt.decode(token, obtener_configuracion().jwt_secreto, algorithms=[ALGORITMO_JWT])
        return int(datos["sub"])
    except ExpiredSignatureError as error:
        raise SesionExpirada() from error
    except (JWTError, KeyError, ValueError) as error:
        raise NoAutenticado() from error


def obtener_usuario_actual(
    sesion: SesionBD, token: Annotated[str | None, Depends(_esquema_oauth2)]
) -> Usuario:
    """Dependencia: el usuario dueño del token.

    El usuario y su rol se leen de la base en cada petición, no del token: si un
    administrador lo desactiva o le cambia el rol, el cambio aplica de inmediato.
    """
    if not token:
        raise NoAutenticado()
    usuario = sesion.get(Usuario, leer_token(token))
    if usuario is None or not usuario.activo:
        raise NoAutenticado()
    return usuario


UsuarioActual = Annotated[Usuario, Depends(obtener_usuario_actual)]


def requiere_roles(*roles: Rol) -> Callable[[Usuario], Usuario]:
    """Crea una dependencia que solo deja pasar a usuarios con alguno de ``roles``."""
    permitidos = frozenset(roles)

    def _verificar_rol(usuario: UsuarioActual) -> Usuario:
        if usuario.rol not in permitidos:
            raise PermisoDenegado()
        return usuario

    return _verificar_rol


SoloAdministrador = Annotated[Usuario, Depends(requiere_roles(Rol.ADMINISTRADOR))]
AdministradorUOperador = Annotated[
    Usuario, Depends(requiere_roles(Rol.ADMINISTRADOR, Rol.OPERADOR))
]
