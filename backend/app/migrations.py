"""Startup migrations: Alembic upgrade plus an additive ensure_schema fallback."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

BACKEND_DIR = Path(__file__).resolve().parent.parent

# The revision that captures the full pre-Alembic schema; legacy databases
# created by Base.metadata.create_all are stamped with it instead of running it.
BASELINE_REVISION = "0001"

# (table, column, SQL type spelled so both SQLite and PostgreSQL accept it)
EXPECTED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("users", "telegram_chat_id", "VARCHAR(50)"),
    ("users", "language", "VARCHAR(5) DEFAULT 'uk'"),
    ("service_intervals", "last_notified_at", "DATE"),
)


def ensure_schema(engine: Engine) -> None:
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


def _alembic_config(engine: Engine) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option(
        "sqlalchemy.url", engine.url.render_as_string(hide_password=False)
    )
    return config


def run_migrations(engine: Engine) -> None:
    """Bring the database schema up to the latest Alembic revision.

    Called on API and bot startup instead of ``Base.metadata.create_all``:

    1. A legacy database (has ``users`` but no ``alembic_version``) is stamped
       with the baseline revision so the upgrade does not re-create its tables.
    2. ``alembic upgrade head`` applies any pending revisions (a fresh database
       gets the whole schema from the baseline).
    3. ``ensure_schema`` stays as a fallback for old dev databases whose
       pre-Alembic tables miss additive columns.
    """
    config = _alembic_config(engine)
    tables = set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        # Hand our live connection to alembic/env.py so migrations run on the
        # exact database this engine points at (crucial for test engines).
        config.attributes["connection"] = connection
        if "alembic_version" not in tables and "users" in tables:
            command.stamp(config, BASELINE_REVISION)
        command.upgrade(config, "head")
    ensure_schema(engine)
