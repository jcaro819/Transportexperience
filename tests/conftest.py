"""Configuración común de los tests.

Los tests que tocan base de datos usan Postgres, en una base separada dentro del mismo
contenedor de docker compose (DATABASE_URL_PRUEBAS). Nunca SQLite: el modelo usa funciones
propias de Postgres (bloqueo de fila, restricciones de exclusión).

Los tests de lógica pura no piden los fixtures ``base_datos_pruebas`` ni ``sesion`` y
corren sin Docker.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

# Se fijan antes de importar la aplicación. Las variables de entorno tienen prioridad
# sobre el archivo .env.
os.environ["ENTORNO"] = "pruebas"
os.environ["JWT_SECRETO"] = "secreto-solo-para-tests"
os.environ["PAGOS_PROVEEDOR"] = "falso"
os.environ["GPS_FUENTE"] = "simulador"

from app.config import Configuracion  # noqa: E402


def _url_pruebas() -> URL:
    """URL de la base de pruebas. Se niega a devolver una base que no sea de pruebas."""
    config = Configuracion()
    if config.database_url_pruebas:
        url = make_url(config.database_url_pruebas)
    else:
        url = make_url(config.database_url)
        url = url.set(database=f"{url.database}_pruebas")
    if not (url.database or "").endswith("_pruebas"):
        raise RuntimeError(
            f"La base de los tests debe terminar en '_pruebas' y es '{url.database}'. "
            "Revisa DATABASE_URL_PRUEBAS en el .env."
        )
    return url


URL_PRUEBAS = _url_pruebas()
# La aplicación (app.db) se conectará a la base de pruebas, no a la de desarrollo.
os.environ["DATABASE_URL"] = URL_PRUEBAS.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def base_datos_pruebas() -> URL:
    """Garantiza que la base de pruebas exista y tenga todas las migraciones aplicadas.

    Requiere ``docker compose up -d``. Si la base no existe, la crea. Las tablas se crean
    con las mismas migraciones de Alembic que la base de desarrollo, no con create_all:
    así los tests también prueban la migración.
    """
    mantenimiento = create_engine(
        URL_PRUEBAS.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )
    try:
        with mantenimiento.connect() as conexion:
            existe = conexion.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :nombre"),
                {"nombre": URL_PRUEBAS.database},
            ).scalar()
            if not existe:
                conexion.execute(text(f'CREATE DATABASE "{URL_PRUEBAS.database}"'))
    finally:
        mantenimiento.dispose()

    raiz = Path(__file__).resolve().parent.parent
    configuracion_alembic = Config(str(raiz / "alembic.ini"))
    configuracion_alembic.set_main_option("script_location", str(raiz / "alembic"))
    command.upgrade(configuracion_alembic, "head")
    return URL_PRUEBAS


@pytest.fixture
def sesion(base_datos_pruebas: URL) -> Iterator[Session]:
    """Sesión dentro de una transacción que se revierte al final del test.

    Cada test empieza con la base vacía y no deja datos. Los ``begin_nested()`` del test
    se vuelven SAVEPOINTs, así un test puede provocar un error de integridad a propósito
    y seguir usando la sesión.
    """
    from app.db import motor

    with motor.connect() as conexion:
        transaccion = conexion.begin()
        with Session(bind=conexion, join_transaction_mode="create_savepoint") as sesion:
            yield sesion
        transaccion.rollback()
