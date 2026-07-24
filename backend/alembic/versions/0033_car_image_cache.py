"""Per-car cached car photo (Wikimedia CC0).

Adds the image cache columns to cars: image_url / image_expires_at /
image_checked_at / image_missing. The resolved photo URL is cached so we resolve
once per car rather than on every dashboard load.

Revision ID: 0033
Revises: 0032
"""

from alembic import op
import sqlalchemy as sa

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("image_url", sa.Text(), None),
    ("image_expires_at", sa.DateTime(), None),
    ("image_checked_at", sa.DateTime(), None),
    ("image_missing", sa.Boolean(), sa.text("0")),
)


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    existing = _columns("cars")
    for name, type_, default in _COLUMNS:
        if name in existing:
            continue
        if default is not None:
            op.add_column(
                "cars",
                sa.Column(name, type_, nullable=False, server_default=default),
            )
        else:
            op.add_column("cars", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    existing = _columns("cars")
    for name, _type, _default in reversed(_COLUMNS):
        if name in existing:
            op.drop_column("cars", name)
