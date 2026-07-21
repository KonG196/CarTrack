"""Tyre-age nudge dedup stamp on tire sets.

``age_reminded_year`` holds the calendar year an «your tyres are N years old»
reminder was last sent for a set, so the nudge fires at most once per year.

Revision ID: 0024
Revises: 0023
"""

from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    if "age_reminded_year" not in _columns("tire_sets"):
        op.add_column("tire_sets", sa.Column("age_reminded_year", sa.Integer(), nullable=True))


def downgrade() -> None:
    if "age_reminded_year" in _columns("tire_sets"):
        op.drop_column("tire_sets", "age_reminded_year")
