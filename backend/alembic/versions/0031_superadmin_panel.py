"""Superadmin panel: user status flags + admin audit log.

Adds users.is_superadmin / blocked / blocked_reason and the admin_audit_log
table that records every action taken in the panel.

Revision ID: 0031
Revises: 0030
"""

from alembic import op
import sqlalchemy as sa

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

_USER_COLUMNS = (
    ("is_superadmin", sa.Boolean(), sa.text("0")),
    ("blocked", sa.Boolean(), sa.text("0")),
    ("blocked_reason", sa.String(length=500), None),
)


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    existing = _columns("users")
    for name, type_, default in _USER_COLUMNS:
        if name in existing:
            continue
        column = sa.Column(name, type_, nullable=(default is None))
        if default is not None:
            column = sa.Column(name, type_, nullable=False, server_default=default)
        op.add_column("users", column)

    if "admin_audit_log" not in _tables():
        op.create_table(
            "admin_audit_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "actor_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("action", sa.String(length=40), nullable=False),
            sa.Column(
                "target_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("target_email", sa.String(length=255), nullable=True),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index(
            "ix_admin_audit_log_actor_id", "admin_audit_log", ["actor_id"]
        )
        op.create_index(
            "ix_admin_audit_log_target_user_id",
            "admin_audit_log",
            ["target_user_id"],
        )
        op.create_index(
            "ix_admin_audit_log_created_at", "admin_audit_log", ["created_at"]
        )


def downgrade() -> None:
    if "admin_audit_log" in _tables():
        op.drop_table("admin_audit_log")
    existing = _columns("users")
    for name, _type, _default in reversed(_USER_COLUMNS):
        if name in existing:
            op.drop_column("users", name)
