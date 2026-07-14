"""Add the log_photos table (photos attached to log entries).

The create is skipped when the table already exists: an unstamped dev
database born from ``Base.metadata.create_all`` at current code state has
log_photos already, yet run_migrations stamps it with the baseline only.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-15 00:13:54.182090

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if 'log_photos' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table('log_photos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('log_entry_id', sa.Integer(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['log_entry_id'], ['log_entries.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('log_photos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_log_photos_log_entry_id'), ['log_entry_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('log_photos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_log_photos_log_entry_id'))

    op.drop_table('log_photos')
