"""Add the expense_details table (a category per expense log entry).

Existing expense rows are left untouched: they simply have no category row
until one is written. The create is skipped when the table already exists:
an unstamped dev database born from ``Base.metadata.create_all`` at current
code state has expense_details already, yet run_migrations stamps it with
the baseline only.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if 'expense_details' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table('expense_details',
    sa.Column('log_entry_id', sa.Integer(), nullable=False),
    sa.Column('category', sa.String(length=50), nullable=False),
    sa.ForeignKeyConstraint(['log_entry_id'], ['log_entries.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('log_entry_id')
    )


def downgrade() -> None:
    op.drop_table('expense_details')
