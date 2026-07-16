"""Axle-rotation tracking on tire sets.

``odometer_at_rotation`` is the baseline the 10k rotation nudge counts from
(stamped on install, reset by the rotate action); ``rotation_reminded_km`` is
the last km-multiple nudged about, so the reminder is not repeated daily.

Revision ID: 0019
Revises: 0018
"""

from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    existing = _columns("tire_sets")
    for column in ("odometer_at_rotation", "rotation_reminded_km"):
        if column not in existing:
            op.add_column("tire_sets", sa.Column(column, sa.Integer(), nullable=True))


def downgrade() -> None:
    existing = _columns("tire_sets")
    for column in ("odometer_at_rotation", "rotation_reminded_km"):
        if column in existing:
            op.drop_column("tire_sets", column)
