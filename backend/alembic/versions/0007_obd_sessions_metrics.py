"""Add the obd_sessions and obd_metrics tables (Car Scanner log import).

One row per imported CSV in ``obd_sessions``, one row per canonical metric in
``obd_metrics``. The metric series is stored as JSON downsampled to <= 200
points rather than one row per sample: a single 40-minute log at 1 Hz would
otherwise be hundreds of thousands of rows nobody reads back. The raw CSV is
not stored at all.

Each create is skipped when the table already exists: an unstamped dev
database born from ``Base.metadata.create_all`` at current code state has
both tables already, yet run_migrations stamps it with the baseline only.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-15 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())

    if 'obd_sessions' not in tables:
        op.create_table('obd_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('car_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('recorded_at', sa.DateTime(), nullable=True),
        sa.Column('duration_s', sa.Float(), nullable=False),
        sa.Column('sample_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['car_id'], ['cars.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('obd_sessions', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_obd_sessions_car_id'), ['car_id'], unique=False)

    if 'obd_metrics' not in tables:
        op.create_table('obd_metrics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=50), nullable=False),
        sa.Column('unit', sa.String(length=20), nullable=False),
        sa.Column('min', sa.Float(), nullable=False),
        sa.Column('max', sa.Float(), nullable=False),
        sa.Column('avg', sa.Float(), nullable=False),
        sa.Column('last', sa.Float(), nullable=False),
        sa.Column('series', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['obd_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('obd_metrics', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_obd_metrics_session_id'), ['session_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('obd_metrics', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_obd_metrics_session_id'))
    op.drop_table('obd_metrics')

    with op.batch_alter_table('obd_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_obd_sessions_car_id'))
    op.drop_table('obd_sessions')
