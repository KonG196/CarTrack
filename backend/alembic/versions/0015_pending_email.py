"""Let a user change their email, safely.

The address is not swapped when it is typed — it is parked in `pending_email`
until a code sent to it comes back. Login is gated on a verified address, so
writing an unconfirmed one straight into `users.email` would lock the user out
of their own account over a typo, with no way back in.

Revision ID: 0015
Revises: 0014
"""

from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    if "pending_email" not in _columns("users"):
        op.add_column("users", sa.Column("pending_email", sa.String(255), nullable=True))


def downgrade() -> None:
    if "pending_email" in _columns("users"):
        op.drop_column("users", "pending_email")
