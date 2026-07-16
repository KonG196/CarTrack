"""Per-user master switch for interval reminders.

The weekly digest already had its own toggle (`digest_enabled`); the due/overdue
reminders did not. Default true — the whole point of the tracker is being told
before something lapses, so reminders are on until the user turns them off.

Revision ID: 0016
Revises: 0015
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import true

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    if "reminders_enabled" not in _columns("users"):
        op.add_column(
            "users",
            sa.Column(
                "reminders_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=true(),
            ),
        )


def downgrade() -> None:
    if "reminders_enabled" in _columns("users"):
        op.drop_column("users", "reminders_enabled")
