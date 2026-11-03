"""Instantánea de las actas (arreglo de HU-11).

``actas.instantanea`` guarda, al crear el acta, la copia de lo que dice (nombres, vehículo,
fechas...), ya formateada. El PDF se arma solo desde ahí: si alguien cambia su nombre
después, el SHA-256 de un acta ya aceptada sigue coincidiendo.

Nullable a propósito: las actas creadas antes de esta migración no la tienen, y para ellas
el PDF se sigue armando con los datos actuales (como hasta ahora).

Revision ID: ce778c5c8489
Revises: 845c1b8b60d3
Create Date: 2026-10-27 09:46:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "ce778c5c8489"
down_revision: str | Sequence[str] | None = "845c1b8b60d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Agrega ``actas.instantanea``."""
    op.add_column("actas", sa.Column("instantanea", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    """Quita ``actas.instantanea``."""
    op.drop_column("actas", "instantanea")
