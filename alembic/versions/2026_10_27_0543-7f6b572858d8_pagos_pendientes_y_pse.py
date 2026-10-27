"""Pagos pendientes y PSE (HU-05).

Generada con --autogenerate y ajustada a mano:

- ``pagos.url_redireccion``: la página del banco a la que PSE envía al cliente.
- ``pagos.bloqueo_original_hasta``: el vencimiento de 15 minutos de la operación al empezar
  el cobro, para restaurarlo si el pago falla (decisión 1 de HU-05).
- Parámetro ``max_minutos_pago_pendiente`` = 60: cuánto puede extenderse el bloqueo de una
  operación mientras su pago sigue pendiente (configurable en base de datos, SRS 3.5.3).

Revision ID: 7f6b572858d8
Revises: c74d60acf0af
Create Date: 2026-10-27 05:43:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7f6b572858d8"
down_revision: str | Sequence[str] | None = "c74d60acf0af"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PARAMETROS = sa.table(
    "parametros_sistema",
    sa.column("clave", sa.String),
    sa.column("valor", sa.Integer),
    sa.column("descripcion", sa.Text),
)


def upgrade() -> None:
    """Agrega las columnas de PSE y del bloqueo, y el máximo de minutos con pago pendiente."""
    op.add_column("pagos", sa.Column("url_redireccion", sa.String(length=500), nullable=True))
    op.add_column(
        "pagos", sa.Column("bloqueo_original_hasta", sa.DateTime(timezone=True), nullable=True)
    )
    op.bulk_insert(
        _PARAMETROS,
        [
            {
                "clave": "max_minutos_pago_pendiente",
                "valor": 60,
                "descripcion": (
                    "Máximo de minutos que una reserva o compra sigue apartada mientras su "
                    "pago está pendiente (p. ej., PSE). Después expira."
                ),
            }
        ],
    )


def downgrade() -> None:
    """Quita el parámetro y las columnas."""
    op.execute("DELETE FROM parametros_sistema WHERE clave = 'max_minutos_pago_pendiente'")
    op.drop_column("pagos", "bloqueo_original_hasta")
    op.drop_column("pagos", "url_redireccion")
