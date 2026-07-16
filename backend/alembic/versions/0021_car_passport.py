"""Public QR passport: a per-car token and the fields the passport shows.

``public_token`` is the unguessable key the tokenless public route accepts (NULL
until minted, cleared to revoke). The rest are the owner-entered passport facts:
contact phone, ОСЦПВ number and expiry, tyre pressure, fuel approval.

Revision ID: 0021
Revises: 0020
"""

from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


_COLUMNS = {
    "public_token": sa.Column("public_token", sa.String(length=32), nullable=True),
    "contact_phone": sa.Column("contact_phone", sa.String(length=30), nullable=True),
    "insurance_number": sa.Column("insurance_number", sa.String(length=50), nullable=True),
    "insurance_until": sa.Column("insurance_until", sa.Date(), nullable=True),
    "tire_pressure": sa.Column("tire_pressure", sa.String(length=50), nullable=True),
    "fuel_approval": sa.Column("fuel_approval", sa.String(length=120), nullable=True),
}


def upgrade() -> None:
    existing = _columns("cars")
    for name, column in _COLUMNS.items():
        if name not in existing:
            op.add_column("cars", column)
    indexes = {ix["name"] for ix in sa.inspect(op.get_bind()).get_indexes("cars")}
    if "ix_cars_public_token" not in indexes:
        op.create_index("ix_cars_public_token", "cars", ["public_token"], unique=True)


def downgrade() -> None:
    indexes = {ix["name"] for ix in sa.inspect(op.get_bind()).get_indexes("cars")}
    if "ix_cars_public_token" in indexes:
        op.drop_index("ix_cars_public_token", table_name="cars")
    existing = _columns("cars")
    for name in _COLUMNS:
        if name in existing:
            op.drop_column("cars", name)
