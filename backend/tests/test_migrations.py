"""Startup migration: ensure_schema adds the Stage 2 columns idempotently."""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from app.migrations import ensure_schema


def _column_names(engine, table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)}


def test_ensure_schema_adds_missing_columns_and_is_idempotent() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # simulate a pre-Stage-2 database: tables exist without the new columns
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255))")
        )
        connection.execute(
            text("CREATE TABLE service_intervals (id INTEGER PRIMARY KEY)")
        )

    ensure_schema(engine)
    assert "telegram_chat_id" in _column_names(engine, "users")
    assert "last_notified_at" in _column_names(engine, "service_intervals")

    # a second run must be a no-op, not a crash
    ensure_schema(engine)
    assert "telegram_chat_id" in _column_names(engine, "users")

    engine.dispose()


def test_ensure_schema_is_a_noop_on_a_fresh_schema(db_engine) -> None:
    ensure_schema(db_engine)
    assert "telegram_chat_id" in _column_names(db_engine, "users")
    assert "last_notified_at" in _column_names(db_engine, "service_intervals")
