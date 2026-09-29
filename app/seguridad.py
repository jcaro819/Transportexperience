"""Seguridad: hash de contraseñas. JWT y dependencias de permisos llegan en el paso 6 (HU-12)."""

import logging

from passlib.context import CryptContext

# passlib 1.7.4 intenta leer bcrypt.__about__, que bcrypt 4.1+ ya no tiene. Lo registra
# como error aunque el hash funciona bien; se silencia para no ensuciar la salida.
logging.getLogger("passlib.handlers.bcrypt").setLevel(logging.ERROR)

_contexto = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hashear_contrasena(contrasena: str) -> str:
    """Devuelve el hash bcrypt de ``contrasena``. Nunca se guarda la contraseña en claro."""
    return _contexto.hash(contrasena)


def verificar_contrasena(contrasena: str, hash_guardado: str) -> bool:
    """Indica si ``contrasena`` corresponde a ``hash_guardado``."""
    return _contexto.verify(contrasena, hash_guardado)
