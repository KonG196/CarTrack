"""Persisted notification history for the in-app centre.

One row per (user, stable notification key), reconciled from the computed nudges
on every read so "past notifications" survives after the condition clears.

Revision ID: 0032
Revises: 0031
"""

from alembic import op
import sqlalchemy as sa

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "notification_log" in _tables():
        return
    op.create_table(
        "notification_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("notif_key", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("car_id", sa.Integer(), nullable=True),
        sa.Column("car_label", sa.String(length=120), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_active_at", sa.DateTime(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "notif_key", name="uq_notiflog_user_key"),
    )
    op.create_index(
        "ix_notification_log_user_id", "notification_log", ["user_id"]
    )
    op.create_index(
        "ix_notification_log_created_at", "notification_log", ["created_at"]
    )


def downgrade() -> None:
    if "notification_log" in _tables():
        op.drop_table("notification_log")
