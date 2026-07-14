"""Add car_invites: hashed, single-use share links with a 7-day TTL.

Nothing is backfilled and nothing is rewritten: an invite only ever comes
from someone pressing «Запросити» after this migration runs, so the table
starts empty on every database.

Only the bcrypt hash of a token is stored, so this table is not sensitive in
the way a token table usually is — but it is still the record of how each
member got in (``used_by``/``used_at``), which is why spent rows are kept
rather than deleted.

The create is skipped when the table already exists: an unstamped dev
database born from ``Base.metadata.create_all`` at current code state has it
already, yet run_migrations stamps it with the baseline only.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-15 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    if 'car_invites' not in sa.inspect(bind).get_table_names():
        op.create_table('car_invites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('car_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=10), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_by', sa.Integer(), nullable=True),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['car_id'], ['cars.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['used_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('car_invites', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_car_invites_car_id'), ['car_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('car_invites', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_car_invites_car_id'))
    op.drop_table('car_invites')
