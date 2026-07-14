"""Add car_members (+ owner backfill), log_entries.author_id, users.display_name.

The sharing epic keeps ``cars.user_id`` as the authoritative owner, so this
migration adds membership beside it rather than replacing it: every existing
car gets exactly one ``car_members`` row for its owner, which is what makes
the members list a single query later.

The backfill is idempotent by a NOT EXISTS guard rather than by a flag, so a
half-applied run, a re-run, or a database that already has some memberships
all converge on the same state; an existing row is never rewritten.

``log_entries.author_id`` is left NULL for every existing row on purpose: the
history predates authorship and there is no honest way to say who wrote it.
Filling it with ``cars.user_id`` would look right and be a guess.

Each create/add is skipped when it already exists: an unstamped dev database
born from ``Base.metadata.create_all`` at current code state has them
already, yet run_migrations stamps it with the baseline only.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-15 16:00:00.000000

"""
import datetime as dt
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def _author_id_column(dialect: str) -> sa.Column:
    """The author_id column, with its foreign key where one can be added.

    SQLite cannot ALTER a constraint onto an existing table — alembic would
    need batch mode, which rebuilds log_entries by copy-and-move. That is a
    poor trade for a nullable bookkeeping column: the rebuild would put the
    real service history through a copy for a constraint SQLite does not
    enforce by default anyway. So SQLite gets the plain column (a database
    created fresh from the models still has the FK), PostgreSQL gets the FK.
    """
    if dialect == 'sqlite':
        return sa.Column('author_id', sa.Integer(), nullable=True)
    return sa.Column(
        'author_id',
        sa.Integer(),
        sa.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )

# One owner membership per car, for cars that do not have one yet.
BACKFILL_OWNERS = sa.text(
    """
    INSERT INTO car_members (car_id, user_id, role, created_at)
    SELECT c.id, c.user_id, 'owner', :created_at
    FROM cars c
    WHERE NOT EXISTS (
        SELECT 1 FROM car_members m
        WHERE m.car_id = c.id AND m.user_id = c.user_id
    )
    """
).bindparams(sa.bindparam('created_at', type_=sa.DateTime()))


def upgrade() -> None:
    bind = op.get_bind()

    if 'car_members' not in sa.inspect(bind).get_table_names():
        op.create_table('car_members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('car_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['car_id'], ['cars.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('car_id', 'user_id', name='uq_car_members_car_user')
        )
        with op.batch_alter_table('car_members', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_car_members_car_id'), ['car_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_car_members_user_id'), ['user_id'], unique=False)

    # Re-inspect: the table above may have just appeared.
    inspector = sa.inspect(bind)
    new_columns = (
        ('log_entries', _author_id_column(bind.dialect.name)),
        ('users', sa.Column('display_name', sa.String(length=80), nullable=True)),
    )
    for table, column in new_columns:
        existing = {col['name'] for col in inspector.get_columns(table)}
        if column.name not in existing:
            op.add_column(table, column)

    indexes = {index['name'] for index in inspector.get_indexes('log_entries')}
    if 'ix_log_entries_author_id' not in indexes:
        op.create_index('ix_log_entries_author_id', 'log_entries', ['author_id'], unique=False)

    bind.execute(BACKFILL_OWNERS, {'created_at': dt.datetime.now(dt.timezone.utc)})


def downgrade() -> None:
    op.drop_index('ix_log_entries_author_id', table_name='log_entries')
    op.drop_column('log_entries', 'author_id')
    op.drop_column('users', 'display_name')

    with op.batch_alter_table('car_members', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_car_members_user_id'))
        batch_op.drop_index(batch_op.f('ix_car_members_car_id'))
    op.drop_table('car_members')
