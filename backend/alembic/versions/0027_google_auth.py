"""Google sign-in support.

Two changes so an account can exist without a password:

* ``users.auth_provider`` — «password» (the default, email+password) or
  «google» (created via Google Sign-In).
* ``users.hashed_password`` becomes nullable — a Google account has no password
  of its own. Existing rows keep theirs; only Google accounts store NULL.

Revision ID: 0027
Revises: 0026
"""

from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    if "auth_provider" not in _columns("users"):
        op.add_column(
            "users",
            sa.Column(
                "auth_provider",
                sa.String(length=20),
                nullable=False,
                server_default=sa.text("'password'"),
            ),
        )
    # Drop the NOT NULL on hashed_password. Batch mode makes this work on SQLite
    # (which can't ALTER a column in place) as well as PostgreSQL.
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "hashed_password",
            existing_type=sa.String(length=255),
            nullable=True,
        )


def downgrade() -> None:
    # Restore NOT NULL only if no NULLs exist (a Google account would block it);
    # backfill an empty string so the constraint can go back on cleanly.
    op.execute("UPDATE users SET hashed_password = '' WHERE hashed_password IS NULL")
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "hashed_password",
            existing_type=sa.String(length=255),
            nullable=False,
        )
    if "auth_provider" in _columns("users"):
        op.drop_column("users", "auth_provider")
