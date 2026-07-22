"""Per-user UI language.

``users.language`` ('en' | 'uk') stores the language a user picked, which also
decides the language of their emails, Telegram messages and API error details.
Existing rows default to 'uk' so nobody is switched silently; new accounts are
created with 'en' (the app default) by the register endpoint.

Revision ID: 0025
Revises: 0024
"""

from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    if "language" not in _columns("users"):
        op.add_column(
            "users",
            sa.Column(
                "language",
                sa.String(length=5),
                nullable=False,
                server_default=sa.text("'uk'"),
            ),
        )


def downgrade() -> None:
    if "language" in _columns("users"):
        op.drop_column("users", "language")
