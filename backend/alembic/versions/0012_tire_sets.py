"""Add the tire_sets table (seasonal tire sets per car).

The create is skipped when the table already exists: an unstamped dev database
born from ``Base.metadata.create_all`` at current code state has it already,
yet run_migrations stamps it with the baseline only (see 0006).

``odometer_at_install`` is nullable because a set starts on the shelf: the
stamp is written by POST /api/tires/{id}/install, from the car's odometer at
that moment, and is the only thing a set's mileage is derived from.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-15 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0012'
down_revision: Union[str, None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())

    if 'tire_sets' not in existing_tables:
        op.create_table('tire_sets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('car_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('season', sa.String(length=10), nullable=False),
        sa.Column('size', sa.String(length=30), nullable=True),
        sa.Column('dot_year', sa.Integer(), nullable=True),
        sa.Column('purchased_at', sa.Date(), nullable=True),
        sa.Column('odometer_at_install', sa.Integer(), nullable=True),
        sa.Column('is_installed', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['car_id'], ['cars.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('tire_sets', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_tire_sets_car_id'), ['car_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('tire_sets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tire_sets_car_id'))

    op.drop_table('tire_sets')
