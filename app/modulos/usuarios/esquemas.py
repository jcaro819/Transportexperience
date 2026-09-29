"""Esquemas de entrada y salida del módulo de usuarios (HU-12). Son el contrato con el frontend."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.modulos.usuarios.modelos import Rol

# Validación simple, sin dependencias nuevas: algo@algo.algo. Se guarda en minúsculas.
Correo = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_lower=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    ),
    Field(examples=["carla@correo.com"]),
]


def _cabe_en_bcrypt(contrasena: str) -> str:
    # bcrypt solo usa los primeros 72 bytes; una tilde o una ñ ocupan 2.
    if len(contrasena.encode("utf-8")) > 72:
        raise ValueError("La contraseña es demasiado larga (máximo 72 bytes).")
    return contrasena


Contrasena = Annotated[
    str,
    StringConstraints(min_length=8, max_length=72),
    AfterValidator(_cabe_en_bcrypt),
    Field(description="Mínimo 8 caracteres.", examples=["MiClave2026"]),
]
NombreCompleto = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=150),
    Field(examples=["Carla Cliente"]),
]
Telefono = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^\+?[0-9 ]{7,20}$"),
    Field(examples=["3001234567"]),
]


class RegistroCliente(BaseModel):
    """Registro público. La cuenta creada siempre tiene rol ``cliente``."""

    nombre_completo: NombreCompleto
    correo: Correo
    telefono: Telefono | None = None
    contrasena: Contrasena


class UsuarioCrear(RegistroCliente):
    """Creación por un administrador, con cualquier rol."""

    rol: Rol


class UsuarioActualizar(BaseModel):
    """Cambios parciales hechos por un administrador. Solo se aplican los campos enviados."""

    nombre_completo: NombreCompleto | None = None
    telefono: Telefono | None = None
    rol: Rol | None = None
    activo: bool | None = Field(None, description="false desactiva la cuenta (no se borra).")

    @model_validator(mode="after")
    def _sin_nulos_obligatorios(self) -> "UsuarioActualizar":
        # Omitir un campo = no cambiarlo. Enviarlo en null solo vale para borrar el teléfono.
        for campo in ("nombre_completo", "rol", "activo"):
            if campo in self.model_fields_set and getattr(self, campo) is None:
                raise ValueError(f"'{campo}' no puede ser null; omítelo si no quieres cambiarlo.")
        return self


class UsuarioRespuesta(BaseModel):
    """Usuario tal como lo ve la API. Nunca incluye el hash de la contraseña."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre_completo: str
    correo: str
    telefono: str | None
    rol: Rol
    activo: bool
    creado_en: datetime


class TokenAcceso(BaseModel):
    """Respuesta del inicio de sesión (formato OAuth2, más los datos del usuario)."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expira_en_segundos: int = Field(description="Tras este tiempo hay que iniciar sesión de nuevo.")
    usuario: UsuarioRespuesta
