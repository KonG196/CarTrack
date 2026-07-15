"""Startup migrations: Alembic run_migrations plus the ensure_schema fallback."""

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.migrations import ensure_schema, run_migrations

BASE_TABLES = {
    "users",
    "cars",
    "log_entries",
    "refuel_details",
    "maintenance_details",
    "repair_details",
    "service_intervals",
}


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


@pytest.fixture()
def file_engine(tmp_path) -> Engine:
    engine = create_engine(f"sqlite:///{tmp_path / 'migrate.db'}")
    yield engine
    engine.dispose()


def test_run_migrations_on_empty_database_creates_full_schema(file_engine: Engine) -> None:
    run_migrations(file_engine)
    tables = set(inspect(file_engine).get_table_names())
    assert BASE_TABLES <= tables
    assert "alembic_version" in tables


def test_run_migrations_stamps_a_legacy_create_all_database(file_engine: Engine) -> None:
    # simulate a pre-Alembic database: full schema, no alembic_version table
    Base.metadata.create_all(bind=file_engine)
    assert "alembic_version" not in inspect(file_engine).get_table_names()

    run_migrations(file_engine)  # must stamp + upgrade, not re-create tables

    tables = set(inspect(file_engine).get_table_names())
    assert BASE_TABLES <= tables
    assert "alembic_version" in tables
    with file_engine.connect() as connection:
        version = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert version


def test_run_migrations_is_idempotent(file_engine: Engine) -> None:
    run_migrations(file_engine)
    run_migrations(file_engine)  # a second run must be a no-op, not a crash
    assert BASE_TABLES <= set(inspect(file_engine).get_table_names())


def test_migration_0003_adds_updated_at_and_reset_columns(file_engine: Engine) -> None:
    # simulate a legacy pre-0003 database: raw tables without the new columns
    with file_engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255), "
                "hashed_password VARCHAR(255), telegram_chat_id VARCHAR(50), "
                "created_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE cars (id INTEGER PRIMARY KEY, user_id INTEGER, "
                "brand VARCHAR(100), created_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE log_entries (id INTEGER PRIMARY KEY, car_id INTEGER, "
                "created_at DATETIME)"
            )
        )
        connection.execute(
            text("CREATE TABLE service_intervals (id INTEGER PRIMARY KEY, car_id INTEGER)")
        )

    run_migrations(file_engine)

    assert "updated_at" in _column_names(file_engine, "cars")
    assert "updated_at" in _column_names(file_engine, "log_entries")
    assert "updated_at" in _column_names(file_engine, "service_intervals")
    assert "reset_code_hash" in _column_names(file_engine, "users")
    assert "reset_code_expires_at" in _column_names(file_engine, "users")


def test_patch_stamps_updated_at(client, auth_headers, make_car) -> None:
    import datetime as dt

    car = make_car(current_odometer=10000)
    created = client.post(
        f"/api/cars/{car['id']}/logs",
        json={
            "type": "expense",
            "odometer": 10100,
            "date": dt.date.today().isoformat(),
            "total_cost": 25,
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    created_stamp = created.json()["updated_at"]
    assert created_stamp is not None

    patched = client.patch(
        f"/api/logs/{created.json()['id']}",
        json={"total_cost": 30},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    patched_stamp = patched.json()["updated_at"]
    assert patched_stamp is not None
    assert dt.datetime.fromisoformat(patched_stamp) > dt.datetime.fromisoformat(created_stamp)


def test_detail_only_patch_stamps_updated_at(client, auth_headers, make_car) -> None:
    """Editing only a nested detail row must still bump the log's own stamp
    (column-level onupdate alone would miss it — offline sync keys on this)."""
    import datetime as dt

    car = make_car(current_odometer=10000)
    created = client.post(
        f"/api/cars/{car['id']}/logs",
        json={
            "type": "refuel",
            "odometer": 10100,
            "date": dt.date.today().isoformat(),
            "total_cost": 60,
            "refuel": {"liters": 40, "price_per_liter": 1.5, "is_full_tank": True},
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    created_stamp = created.json()["updated_at"]

    patched = client.patch(
        f"/api/logs/{created.json()['id']}",
        json={"refuel": {"liters": 45}},  # nested detail only, no shared field
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    patched_stamp = patched.json()["updated_at"]
    assert patched_stamp is not None
    assert dt.datetime.fromisoformat(patched_stamp) > dt.datetime.fromisoformat(created_stamp)
