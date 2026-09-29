"""Conexión a la base de datos y clase base de los modelos de SQLAlchemy."""

from collections.abc import Iterator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import obtener_configuracion

# Nombres predecibles para índices y restricciones. Sin esto, Postgres inventa nombres
# y Alembic no puede borrarlos o renombrarlos de forma confiable en migraciones futuras.
CONVENCION_NOMBRES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Clase base de todos los modelos. Alembic la usa para detectar las tablas."""

    metadata = MetaData(naming_convention=CONVENCION_NOMBRES)


# connect_timeout: sin él, una base caída deja cada petición colgada indefinidamente en
# lugar de fallar rápido con un error claro.
motor = create_engine(
    obtener_configuracion().database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 5},
)
SesionLocal = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)


def obtener_sesion() -> Iterator[Session]:
    """Dependencia de FastAPI: abre una sesión por petición y la cierra al terminar."""
    with SesionLocal() as sesion:
        yield sesion
