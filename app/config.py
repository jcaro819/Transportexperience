"""Configuración de la aplicación, leída del entorno y del archivo ``.env``.

La configuración se valida al arrancar: si falta una variable obligatoria o tiene un
valor inválido, la aplicación no inicia y el error dice cuál es. Así un ``.env`` mal
copiado se detecta de inmediato y no a mitad de una petición.

Aquí solo va configuración técnica (conexiones, secretos, proveedores). Las reglas de
negocio configurables (tarifas, zonas, horarios, métodos de pago) viven en la base de
datos, editables por el administrador (SRS 3.5.3).
"""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# El valor de .env.example: si llega aquí, alguien copió el ejemplo sin cambiarlo.
SECRETO_JWT_DE_EJEMPLO = "cambia_este_secreto"
LONGITUD_MINIMA_SECRETO_JWT = 32


class Configuracion(BaseSettings):
    """Variables de entorno de TransportExperience. Ver ``.env.example``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # docker compose también lee el .env (POSTGRES_USER, etc.); se ignoran aquí.
        extra="ignore",
        # Los errores de validación no repiten el valor recibido: podría ser un secreto.
        hide_input_in_errors=True,
    )

    entorno: Literal["desarrollo", "pruebas", "produccion"] = "desarrollo"

    database_url: str
    # Base separada para los tests (mismo contenedor). Su nombre debe terminar en
    # "_pruebas": los tests borran y recrean tablas, y así nunca tocan la base de desarrollo.
    database_url_pruebas: str | None = None

    jwt_secreto: str
    jwt_minutos_expiracion: int = 60

    # Orígenes del frontend que el navegador deja llamar a la API (CORS), separados por
    # comas. Por defecto, los puertos de desarrollo de Vite, React/Next y Angular.
    cors_origenes: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000,http://localhost:4200"

    gps_fuente: Literal["simulador", "dispositivo"] = "simulador"

    pagos_proveedor: Literal["falso", "wompi"] = "falso"
    wompi_llave_publica: str = ""
    wompi_llave_privada: str = ""
    wompi_secreto_eventos: str = ""

    @property
    def lista_cors_origenes(self) -> list[str]:
        return [origen.strip() for origen in self.cors_origenes.split(",") if origen.strip()]

    @field_validator("jwt_secreto")
    @classmethod
    def _secreto_jwt_seguro(cls, valor: str) -> str:
        """Rechaza el secreto de ejemplo y los secretos cortos, fáciles de adivinar."""
        if valor == SECRETO_JWT_DE_EJEMPLO or len(valor) < LONGITUD_MINIMA_SECRETO_JWT:
            raise ValueError(
                f"JWT_SECRETO debe tener al menos {LONGITUD_MINIMA_SECRETO_JWT} caracteres y no "
                "puede ser el valor de ejemplo. Genera uno con: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))" '
                "y ponlo en tu archivo .env"
            )
        return valor

    @field_validator("wompi_llave_publica")
    @classmethod
    def _solo_llave_publica_de_pruebas(cls, valor: str) -> str:
        """Rechaza cualquier llave pública de Wompi que no sea de sandbox."""
        if valor and not valor.startswith("pub_test_"):
            raise ValueError("Solo se permiten llaves de sandbox de Wompi (pub_test_...)")
        return valor

    @field_validator("wompi_llave_privada")
    @classmethod
    def _solo_llave_privada_de_pruebas(cls, valor: str) -> str:
        """Rechaza cualquier llave privada de Wompi que no sea de sandbox."""
        if valor and not valor.startswith("prv_test_"):
            raise ValueError("Solo se permiten llaves de sandbox de Wompi (prv_test_...)")
        return valor


@lru_cache
def obtener_configuracion() -> Configuracion:
    """Devuelve la configuración, construida una sola vez por proceso."""
    return Configuracion()
