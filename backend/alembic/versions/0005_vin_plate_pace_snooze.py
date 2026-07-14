"""Add VIN/plate, the avg-daily-km override and the interval snooze date.

``cars`` gets ``vin``/``plate`` (Task 1) and ``avg_daily_km_override`` (the
manual pace that overrides the computed rolling window); ``service_intervals``
gets ``snoozed_until``, the date the «Нагадати через 7 днів» button books so
the button does something the ordinary 7-day cooldown does not already do.

Existing rows stay NULL, which is exactly the "not set" state all four
columns already mean. Each ADD COLUMN is skipped when the column already
exists: an unstamped dev database born from ``Base.metadata.create_all`` at
current code state has them already, yet run_migrations stamps it with the
baseline only.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    ('cars', sa.Column('vin', sa.String(length=17), nullable=True)),
    ('cars', sa.Column('plate', sa.String(length=16), nullable=True)),
    ('cars', sa.Column('avg_daily_km_override', sa.Float(), nullable=True)),
    ('service_intervals', sa.Column('snoozed_until', sa.Date(), nullable=True)),
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, column in NEW_COLUMNS:
        existing = {col['name'] for col in inspector.get_columns(table)}
        if column.name not in existing:
            op.add_column(table, column)


def downgrade() -> None:
    op.drop_column('service_intervals', 'snoozed_until')
    op.drop_column('cars', 'avg_daily_km_override')
    op.drop_column('cars', 'plate')
    op.drop_column('cars', 'vin')
