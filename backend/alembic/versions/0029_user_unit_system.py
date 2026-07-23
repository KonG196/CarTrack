"""Per-user display unit system.

``users.unit_system`` ('metric' | 'imperial') decides whether distance/volume/
consumption are shown as km·litres·l100km or mi·gallons·mpg. Presentation only —
values are stored metric and converted on display. All rows default to metric.

Revision ID: 0029
Revises: 0028
"""

from alembic import op
import sqlalchemy as sa

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    if "unit_system" not in _columns("users"):
        op.add_column(
            "users",
            sa.Column(
                "unit_system",
                sa.String(length=10),
                nullable=False,
                server_default=sa.text("'metric'"),
            ),
        )


def downgrade() -> None:
    if "unit_system" in _columns("users"):
        op.drop_column("users", "unit_system")
