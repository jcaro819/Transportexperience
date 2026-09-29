"""Entorno de Alembic para TransportExperience.

La URL de la base sale de ``app.config`` (variable DATABASE_URL del ``.env``), la misma
que usa la aplicación, para que nunca apunten a bases distintas.

Comandos habituales:
    alembic revision --autogenerate -m "descripcion"   # genera una migración
    alembic upgrade head                               # aplica las pendientes
    alembic downgrade -1                               # revierte la última
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app import modelos as _modelos  # noqa: F401  registra todas las tablas en Base.metadata
from app.config import obtener_configuracion
from app.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

URL_BASE_DATOS = obtener_configuracion().database_url
target_metadata = Base.metadata


def ejecutar_migraciones_offline() -> None:
    """Genera el SQL de las migraciones sin conectarse (``alembic upgrade head --sql``)."""
    context.configure(
        url=URL_BASE_DATOS,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def ejecutar_migraciones_online() -> None:
    """Aplica las migraciones conectándose a la base."""
    motor = create_engine(URL_BASE_DATOS, poolclass=pool.NullPool)
    with motor.connect() as conexion:
        context.configure(
            connection=conexion,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    ejecutar_migraciones_offline()
else:
    ejecutar_migraciones_online()
