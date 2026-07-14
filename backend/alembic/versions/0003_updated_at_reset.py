"""Add updated_at stamps and password-reset fields.

``cars``/``log_entries``/``service_intervals`` get a nullable ``updated_at``
(existing rows stay NULL — SQLAlchemy stamps it on the next write) and
``users`` gets ``reset_code_hash``/``reset_code_expires_at`` for the
Telegram password-reset flow. Each ADD COLUMN is skipped when the column
already exists: an unstamped dev database born from
``Base.metadata.create_all`` at current code state has them already, yet
run_migrations stamps it with the baseline only.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-15 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    ('cars', sa.Column('updated_at', sa.DateTime(), nullable=True)),
    ('log_entries', sa.Column('updated_at', sa.DateTime(), nullable=True)),
    ('service_intervals', sa.Column('updated_at', sa.DateTime(), nullable=True)),
    ('users', sa.Column('reset_code_hash', sa.String(length=255), nullable=True)),
    ('users', sa.Column('reset_code_expires_at', sa.DateTime(), nullable=True)),
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, column in NEW_COLUMNS:
        existing = {col['name'] for col in inspector.get_columns(table)}
        if column.name not in existing:
            op.add_column(table, column)


def downgrade() -> None:
    op.drop_column('users', 'reset_code_expires_at')
    op.drop_column('users', 'reset_code_hash')
    op.drop_column('service_intervals', 'updated_at')
    op.drop_column('log_entries', 'updated_at')
    op.drop_column('cars', 'updated_at')
