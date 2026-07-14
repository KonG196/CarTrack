"""Add the car_specs and car_documents tables (cheat sheet + document library).

Each create is skipped when the table already exists: an unstamped dev
database born from ``Base.metadata.create_all`` at current code state has both
already, yet run_migrations stamps it with the baseline only.

``car_documents`` deliberately has no link to the ServiceInterval an expiring
document books: the deadline outlives the scan, so the row does not own it.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-15 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())

    if 'car_specs' not in existing_tables:
        op.create_table('car_specs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('car_id', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('value', sa.String(length=200), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['car_id'], ['cars.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('car_specs', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_car_specs_car_id'), ['car_id'], unique=False)

    if 'car_documents' not in existing_tables:
        op.create_table('car_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('car_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=30), nullable=False),
        sa.Column('title', sa.String(length=150), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['car_id'], ['cars.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('car_documents', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_car_documents_car_id'), ['car_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('car_documents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_car_documents_car_id'))

    op.drop_table('car_documents')

    with op.batch_alter_table('car_specs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_car_specs_car_id'))

    op.drop_table('car_specs')
