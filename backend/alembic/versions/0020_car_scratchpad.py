"""Free-text driver's cheat sheet on the car.

Gate codes, service phones, the radio PIN — the text that otherwise lives lost
in phone notes. NULL until the owner writes one.

Revision ID: 0020
Revises: 0019
"""

from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    if "scratchpad" not in _columns("cars"):
        op.add_column("cars", sa.Column("scratchpad", sa.Text(), nullable=True))


def downgrade() -> None:
    if "scratchpad" in _columns("cars"):
        op.drop_column("cars", "scratchpad")
