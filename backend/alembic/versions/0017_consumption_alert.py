"""Dedup state for the fuel-consumption watchdog.

Stores the closing refuel log id of the last consumption spike the bot warned
about, per car, so the same spike is never reported twice. NULL means the car
has never triggered a warning.

Revision ID: 0017
Revises: 0016
"""

from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    if "consumption_alert_log_id" not in _columns("cars"):
        op.add_column(
            "cars",
            sa.Column("consumption_alert_log_id", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    if "consumption_alert_log_id" in _columns("cars"):
        op.drop_column("cars", "consumption_alert_log_id")
