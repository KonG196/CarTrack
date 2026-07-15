"""Add email verification to users.

Existing accounts are marked verified: they predate the gate, so locking them
out would be a regression. New accounts start unverified.

Revision ID: 0014
Revises: 0013
"""

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    existing = _columns("users")

    if "email_verified" not in existing:
        op.add_column(
            "users",
            sa.Column(
                "email_verified",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        op.execute("UPDATE users SET email_verified = 1")
    if "verify_code_hash" not in existing:
        op.add_column("users", sa.Column("verify_code_hash", sa.String(255), nullable=True))
    if "verify_code_expires_at" not in existing:
        op.add_column(
            "users", sa.Column("verify_code_expires_at", sa.DateTime(), nullable=True)
        )


def downgrade() -> None:
    for column in ("verify_code_expires_at", "verify_code_hash", "email_verified"):
        if column in _columns("users"):
            op.drop_column("users", column)
