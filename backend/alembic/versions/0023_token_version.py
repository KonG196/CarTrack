"""Session revocation + code attempt counters.

token_version is embedded in the access token and checked on every request, so
changing/resetting a password revokes older tokens. reset_code_attempts and
verify_code_attempts burn a 6-digit code after a few wrong guesses.

Revision ID: 0023
Revises: 0022
"""

from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

_COLUMNS = ("token_version", "reset_code_attempts", "verify_code_attempts")


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    existing = _columns("users")
    for name in _COLUMNS:
        if name not in existing:
            op.add_column(
                "users",
                sa.Column(name, sa.Integer(), nullable=False, server_default="0"),
            )


def downgrade() -> None:
    existing = _columns("users")
    for name in _COLUMNS:
        if name in existing:
            op.drop_column("users", name)
