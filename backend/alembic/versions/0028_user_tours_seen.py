"""Server-side «which onboarding tours the user has seen».

Moves the tours-seen set off the browser's localStorage onto the account, so a
tour a user has already been shown never re-appears on another device or after
clearing the cache. Stored as a JSON array of tour names in a text column
(``users.tours_seen``), defaulting to an empty list.

Revision ID: 0028
Revises: 0027
"""

from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    if "tours_seen" not in _columns("users"):
        op.add_column(
            "users",
            sa.Column(
                "tours_seen",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
        )


def downgrade() -> None:
    if "tours_seen" in _columns("users"):
        op.drop_column("users", "tours_seen")
