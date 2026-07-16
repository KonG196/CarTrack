"""Per-car dedup state for the seasonal (tires / washer) autumn nudges.

Each column holds the year that nudge last fired, so it goes out at most once
per autumn per car. NULL means it has never fired.

Revision ID: 0018
Revises: 0017
"""

from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    existing = _columns("cars")
    for column in ("tire_reminder_year", "washer_reminder_year"):
        if column not in existing:
            op.add_column("cars", sa.Column(column, sa.Integer(), nullable=True))


def downgrade() -> None:
    existing = _columns("cars")
    for column in ("tire_reminder_year", "washer_reminder_year"):
        if column in existing:
            op.drop_column("cars", column)
