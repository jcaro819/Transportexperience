"""Parámetros de negocio editables en base de datos, con el máximo de días por alquiler.

Generada con --autogenerate y ajustada a mano: se agrega la fila inicial de
``max_dias_alquiler`` (30 días, decisión del equipo para HU-03). El valor queda en la base
y no en el código (SRS 3.5.3).

Revision ID: 1211e36c3ef7
Revises: 05ddce1f9e8a
Create Date: 2026-10-27 04:47:18.672121

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1211e36c3ef7"
down_revision: str | Sequence[str] | None = "05ddce1f9e8a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea ``parametros_sistema`` y su primer parámetro."""
    parametros = op.create_table(
        "parametros_sistema",
        sa.Column("clave", sa.String(length=60), nullable=False),
        sa.Column("valor", sa.Integer(), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("clave", name=op.f("pk_parametros_sistema")),
    )
    op.bulk_insert(
        parametros,
        [
            {
                "clave": "max_dias_alquiler",
                "valor": 30,
                "descripcion": "Máximo de días que puede durar un alquiler, contando inicio y fin.",
            }
        ],
    )


def downgrade() -> None:
    """Borra ``parametros_sistema``."""
    op.drop_table("parametros_sistema")
