"""Add refuel_details.fuel_kind: which fuel a single fill actually was.

Nothing is backfilled, and that is the design rather than a shortcut. NULL
already means «whatever this car runs on», which is the truth about every
existing row: a single-fuel car's fills are its own fuel type, and nobody
could have recorded anything else before this column existed. Writing
car.fuel_type into every row would replace a fact with a guess and would then
go stale the moment a car's fuel type is corrected.

Resolution happens in one place at read time —
``app.services.fuel.effective_fuel_kind`` — so a NULL row and an explicit row
of the car's own type are indistinguishable everywhere downstream.

The ADD COLUMN is skipped when the column already exists: an unstamped dev
database born from ``Base.metadata.create_all`` at current code state has it
already, yet run_migrations stamps it with the baseline only. It is skipped
just as quietly when ``refuel_details`` is missing altogether — a database
stamped at the baseline without ever running it has no such table, and this
revision has no business conjuring one.

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-15 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0013'
down_revision: Union[str, None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    ('refuel_details', sa.Column('fuel_kind', sa.String(length=10), nullable=True)),
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table, column in NEW_COLUMNS:
        if table not in tables:
            continue
        existing = {col['name'] for col in inspector.get_columns(table)}
        if column.name not in existing:
            op.add_column(table, column)


def downgrade() -> None:
    op.drop_column('refuel_details', 'fuel_kind')
