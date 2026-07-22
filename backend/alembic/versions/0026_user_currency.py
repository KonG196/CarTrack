"""Per-user display currency.

``users.currency`` (a 3-letter code) decides which currency symbol is shown for
money. Amounts are never converted — this is a display preference. New accounts
default to USD; existing rows default to UAH so their hryvnia amounts keep their
symbol.

Revision ID: 0026
Revises: 0025
"""

from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    if "currency" not in _columns("users"):
        op.add_column(
            "users",
            sa.Column(
                "currency",
                sa.String(length=3),
                nullable=False,
                server_default=sa.text("'UAH'"),
            ),
        )


def downgrade() -> None:
    if "currency" in _columns("users"):
        op.drop_column("users", "currency")
