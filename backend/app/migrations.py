"""Lightweight startup migrations: additive, idempotent column changes only."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# (table, column, SQL type spelled so both SQLite and PostgreSQL accept it)
EXPECTED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("users", "telegram_chat_id", "VARCHAR(50)"),
    ("service_intervals", "last_notified_at", "DATE"),
)


def ensure_schema(engine: Engine) -> None:
    """Add any missing Stage 2 columns to an already-created database.

    Inspects the live schema and issues plain ``ALTER TABLE ... ADD COLUMN``
    statements for columns that do not exist yet. Safe to call on every
    startup (both the API lifespan and the bot process do): existing columns
    are left untouched and fresh databases already get the full schema from
    ``Base.metadata.create_all``.
    """
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, column, column_type in EXPECTED_COLUMNS:
            if table not in table_names:
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            if column not in existing:
                connection.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
                )
