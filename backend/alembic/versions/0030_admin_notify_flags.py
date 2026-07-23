"""One-shot flags for the owner's new-activity emails.

Four booleans on users, all default False, that latch after the corresponding
admin alert fires once (signup / first car / first verification / first OCR).

Revision ID: 0030
Revises: 0029
"""

from alembic import op
import sqlalchemy as sa

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

_FLAGS = (
    "admin_notified_signup",
    "admin_notified_first_car",
    "admin_notified_verified",
    "admin_notified_first_ocr",
)


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    existing = _columns("users")
    for flag in _FLAGS:
        if flag not in existing:
            op.add_column(
                "users",
                sa.Column(
                    flag, sa.Boolean(), nullable=False, server_default=sa.text("0")
                ),
            )


def downgrade() -> None:
    existing = _columns("users")
    for flag in _FLAGS:
        if flag in existing:
            op.drop_column("users", flag)
