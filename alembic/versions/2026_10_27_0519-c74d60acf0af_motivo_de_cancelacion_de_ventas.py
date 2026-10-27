"""Motivo de cancelación de las ventas (HU-04).

Igual que en alquileres: guarda por qué se canceló una venta. Lo escribe el cliente al
desistir, o el sistema cuando una unidad entró en mantenimiento antes de aprobarse el
pago y hubo que devolver el dinero (decisión 2 del Sprint 2).

Revision ID: c74d60acf0af
Revises: 1211e36c3ef7
Create Date: 2026-10-27 05:19:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c74d60acf0af"
down_revision: str | Sequence[str] | None = "1211e36c3ef7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Agrega ``ventas.motivo_cancelacion``."""
    op.add_column("ventas", sa.Column("motivo_cancelacion", sa.Text(), nullable=True))


def downgrade() -> None:
    """Quita ``ventas.motivo_cancelacion``."""
    op.drop_column("ventas", "motivo_cancelacion")
