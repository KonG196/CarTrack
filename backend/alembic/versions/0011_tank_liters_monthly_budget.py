"""Add the tank volume and the monthly budget to cars.

``tank_liters`` is the usable tank in liters — the only input of the full-tank
range estimate (services/fuel.py:compute_range_km). ``monthly_budget`` is the
owner's spending limit for a calendar month, in ₴.

Both stay NULL on existing rows, which is exactly what «not set» means for
each: no range card and no budget card, rather than a card full of zeros.
NULL is deliberately not 0 for the budget — a zero limit would be a budget
one can only ever be over.

Each ADD COLUMN is skipped when the column already exists: an unstamped dev
database born from ``Base.metadata.create_all`` at current code state has them
already, yet run_migrations stamps it with the baseline only (see 0002/0003).

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0011'
down_revision: Union[str, None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    ('cars', sa.Column('tank_liters', sa.Float(), nullable=True)),
    ('cars', sa.Column('monthly_budget', sa.Numeric(precision=10, scale=2), nullable=True)),
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, column in NEW_COLUMNS:
        existing = {col['name'] for col in inspector.get_columns(table)}
        if column.name not in existing:
            op.add_column(table, column)


def downgrade() -> None:
    op.drop_column('cars', 'monthly_budget')
    op.drop_column('cars', 'tank_liters')
