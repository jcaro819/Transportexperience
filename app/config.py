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


class Configuracion(BaseSettings):
    """Variables de entorno de TransportExperience. Ver ``.env.example``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # docker compose también lee el .env (POSTGRES_USER, etc.); se ignoran aquí.
        extra="ignore",
    )

    entorno: Literal["desarrollo", "pruebas", "produccion"] = "desarrollo"

    database_url: str
    # Base separada para los tests (mismo contenedor). Su nombre debe terminar en
    # "_pruebas": los tests borran y recrean tablas, y así nunca tocan la base de desarrollo.
    database_url_pruebas: str | None = None

    jwt_secreto: str
    jwt_minutos_expiracion: int = 60

    gps_fuente: Literal["simulador", "dispositivo"] = "simulador"

    pagos_proveedor: Literal["falso", "wompi"] = "falso"
    wompi_llave_publica: str = ""
    wompi_llave_privada: str = ""
    wompi_secreto_eventos: str = ""

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
