"""Per-type notification switches.

reminders_enabled keeps meaning «ТО reminders»; each smarter push gets its own
on-by-default flag, so a driver can mute one kind without the others.

Revision ID: 0022
Revises: 0021
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import true

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

_COLUMNS = ("notify_fuel", "notify_seasonal", "notify_rotation")


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    existing = _columns("users")
    for name in _COLUMNS:
        if name not in existing:
            op.add_column(
                "users",
                sa.Column(name, sa.Boolean(), nullable=False, server_default=true()),
            )


def downgrade() -> None:
    existing = _columns("users")
    for name in _COLUMNS:
        if name in existing:
            op.drop_column("users", name)
