"""Clave GPS de cada vehículo y umbral de "sin señal" (HU-08).

- ``vehiculos.hash_clave_gps``: SHA-256 de la clave con la que el dispositivo (o el
  simulador) envía posiciones. Única; la clave en claro nunca se guarda.
- ``vehiculos.fuente_gps``: si la clave es de un dispositivo real o del simulador. Solo se
  aceptan posiciones de la fuente configurada en ``GPS_FUENTE``.
- ``vehiculos.clave_gps_emitida_en``.
- Parámetro ``segundos_sin_senal`` = 30 (configurable en base de datos, SRS 3.5.3).

Escrita a mano a partir de --autogenerate: el CHECK de ``fuente_gps`` se declara explícito,
como en la migración inicial.

Revision ID: 845c1b8b60d3
Revises: 7f6b572858d8
Create Date: 2026-10-27 06:58:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "845c1b8b60d3"
down_revision: str | Sequence[str] | None = "7f6b572858d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PARAMETROS = sa.table(
    "parametros_sistema",
    sa.column("clave", sa.String),
    sa.column("valor", sa.Integer),
    sa.column("descripcion", sa.Text),
)


def upgrade() -> None:
    """Agrega la clave GPS a los vehículos y el umbral de "sin señal"."""
    op.add_column("vehiculos", sa.Column("hash_clave_gps", sa.String(length=64), nullable=True))
    op.add_column("vehiculos", sa.Column("fuente_gps", sa.String(length=30), nullable=True))
    op.add_column(
        "vehiculos", sa.Column("clave_gps_emitida_en", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_unique_constraint(
        op.f("uq_vehiculos_hash_clave_gps"), "vehiculos", ["hash_clave_gps"]
    )
    op.create_check_constraint(
        op.f("ck_vehiculos_fuente_gps"), "vehiculos", "fuente_gps IN ('simulador', 'dispositivo')"
    )
    op.bulk_insert(
        _PARAMETROS,
        [
            {
                "clave": "segundos_sin_senal",
                "valor": 30,
                "descripcion": (
                    "Segundos sin recibir posición después de los cuales un vehículo aparece "
                    "como 'sin señal' en el mapa de la flota."
                ),
            }
        ],
    )


def downgrade() -> None:
    """Quita el parámetro y las columnas."""
    op.execute("DELETE FROM parametros_sistema WHERE clave = 'segundos_sin_senal'")
    op.drop_constraint(op.f("ck_vehiculos_fuente_gps"), "vehiculos", type_="check")
    op.drop_constraint(op.f("uq_vehiculos_hash_clave_gps"), "vehiculos", type_="unique")
    op.drop_column("vehiculos", "clave_gps_emitida_en")
    op.drop_column("vehiculos", "fuente_gps")
    op.drop_column("vehiculos", "hash_clave_gps")
