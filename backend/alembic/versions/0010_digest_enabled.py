"""Add users.digest_enabled: the «/digest on|off» flag for the Sunday digest.

Existing users are opted IN (server_default true), which is the only backfill
that keeps a promise: the flag is new, so nobody has expressed an opinion yet,
and the digest is deliberately silent about a week with no entries — an
opted-in user who does not use the tracker still hears nothing.

The column is NOT NULL with a server-side default so the ADD COLUMN can fill
the existing rows in one statement; ``sa.true()`` is used rather than a raw
``1`` because PostgreSQL will not take an integer default on a boolean.

The ADD COLUMN is skipped when the column already exists: an unstamped dev
database born from ``Base.metadata.create_all`` at current code state has it
already, yet run_migrations stamps it with the baseline only.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-15 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {col['name'] for col in inspector.get_columns('users')}
    if 'digest_enabled' not in existing:
        op.add_column(
            'users',
            sa.Column(
                'digest_enabled',
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )


def downgrade() -> None:
    op.drop_column('users', 'digest_enabled')
