"""Migration 0008: the car_members table and its owner backfill.

The backfill is the risky half of the sharing epic: it runs once, on a real
database with real history behind it. So it is tested twice over — on a
synthetic pre-0008 database (deterministic, several cars) and on a copy of
the actual dev database (the Golf with its 19 real entries), which is the
only place the migration's true starting state exists.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.migrations import _alembic_config, run_migrations

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEV_DB = BACKEND_DIR / "kapot_tracker.db"

# The seeded dev database: one Volkswagen Golf with a real service history.
# Hard-coded on purpose — the point of the check is that the migration moves
# no data, and a count read back from the same file could not show that.
SEEDED_CAR_COUNT = 1
SEEDED_LOG_COUNT = 19

# The revision the dev database sits on before this iteration.
PREVIOUS_REVISION = "0007"


def _upgrade(engine: Engine, revision: str) -> None:
    config = _alembic_config(engine)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)


def _column_names(engine: Engine, table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)}


def _rows(engine: Engine, sql: str) -> list[tuple]:
    with engine.connect() as connection:
        return [tuple(row) for row in connection.execute(text(sql))]


def _scalar(engine: Engine, sql: str):
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar_one()


# Synthetic pre-0008 database


@pytest.fixture()
def pre_0008_engine(tmp_path) -> Engine:
    engine = create_engine(f"sqlite:///{tmp_path / 'pre.db'}")
    _upgrade(engine, PREVIOUS_REVISION)
    with engine.begin() as connection:
        for user_id, email in ((1, "one@example.com"), (2, "two@example.com")):
            connection.execute(
                text(
                    "INSERT INTO users (id, email, hashed_password, created_at) "
                    "VALUES (:id, :email, 'x', '2026-01-01 00:00:00')"
                ),
                {"id": user_id, "email": email},
            )
        for car_id, user_id in ((1, 1), (2, 1), (3, 2)):
            connection.execute(
                text(
                    "INSERT INTO cars (id, user_id, brand, model, year, fuel_type, "
                    "current_odometer, created_at) VALUES (:id, :user_id, 'VW', "
                    "'Golf', 2015, 'diesel', 100, '2026-01-01 00:00:00')"
                ),
                {"id": car_id, "user_id": user_id},
            )
    yield engine
    engine.dispose()


def test_migration_creates_car_members_and_new_columns(pre_0008_engine: Engine) -> None:
    _upgrade(pre_0008_engine, "head")

    assert "car_members" in set(inspect(pre_0008_engine).get_table_names())
    assert "author_id" in _column_names(pre_0008_engine, "log_entries")
    assert "display_name" in _column_names(pre_0008_engine, "users")


def test_migration_backfills_one_owner_membership_per_car(pre_0008_engine: Engine) -> None:
    _upgrade(pre_0008_engine, "head")

    assert _rows(
        pre_0008_engine,
        "SELECT car_id, user_id, role FROM car_members ORDER BY car_id",
    ) == [(1, 1, "owner"), (2, 1, "owner"), (3, 2, "owner")]


def test_backfill_is_idempotent(pre_0008_engine: Engine) -> None:
    _upgrade(pre_0008_engine, "head")
    run_migrations(pre_0008_engine)  # a second pass must add nothing

    assert _scalar(pre_0008_engine, "SELECT COUNT(*) FROM car_members") == 3


def test_backfill_leaves_an_existing_membership_alone(pre_0008_engine: Engine) -> None:
    """A row already there is never duplicated nor rewritten."""
    _upgrade(pre_0008_engine, "head")
    with pre_0008_engine.begin() as connection:
        # user 2 is invited to user 1's car as an editor
        connection.execute(
            text(
                "INSERT INTO car_members (car_id, user_id, role, created_at) "
                "VALUES (1, 2, 'editor', '2026-02-01 00:00:00')"
            )
        )

    run_migrations(pre_0008_engine)

    assert _rows(
        pre_0008_engine,
        "SELECT user_id, role FROM car_members WHERE car_id = 1 ORDER BY user_id",
    ) == [(1, "owner"), (2, "editor")]


def test_author_id_is_null_for_history(pre_0008_engine: Engine) -> None:
    """Legacy entries get no author guessed for them."""
    with pre_0008_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO log_entries (id, car_id, type, odometer, date, "
                "total_cost, created_at) VALUES (1, 1, 'expense', 100, "
                "'2026-01-02', 25, '2026-01-02 00:00:00')"
            )
        )

    _upgrade(pre_0008_engine, "head")

    assert _scalar(pre_0008_engine, "SELECT author_id FROM log_entries WHERE id = 1") is None


# The real dev database


@pytest.fixture()
def dev_db_copy(tmp_path) -> Engine:
    """An engine on a throwaway copy of the dev database (never the original)."""
    if not DEV_DB.is_file():
        pytest.skip("dev database kapot_tracker.db is not present")
    target = tmp_path / "kapot_tracker.db"
    shutil.copy2(DEV_DB, target)
    engine = create_engine(f"sqlite:///{target}")
    yield engine
    engine.dispose()


def test_dev_database_migrates_with_exactly_one_owner_membership(dev_db_copy: Engine) -> None:
    assert _scalar(dev_db_copy, "SELECT COUNT(*) FROM cars") == SEEDED_CAR_COUNT

    run_migrations(dev_db_copy)

    # exactly one owner membership for the seeded Golf, pointing at its owner
    assert _rows(
        dev_db_copy,
        "SELECT m.role, m.user_id = c.user_id FROM car_members m "
        "JOIN cars c ON c.id = m.car_id",
    ) == [("owner", 1)]


def test_dev_database_history_survives_the_migration(dev_db_copy: Engine) -> None:
    assert _scalar(dev_db_copy, "SELECT COUNT(*) FROM log_entries") == SEEDED_LOG_COUNT
    before = _rows(dev_db_copy, "SELECT id, odometer, total_cost FROM log_entries ORDER BY id")

    run_migrations(dev_db_copy)

    assert _scalar(dev_db_copy, "SELECT COUNT(*) FROM log_entries") == SEEDED_LOG_COUNT
    assert _rows(
        dev_db_copy, "SELECT id, odometer, total_cost FROM log_entries ORDER BY id"
    ) == before
    # nothing invented an author for 19 entries that predate authorship
    assert _scalar(
        dev_db_copy, "SELECT COUNT(*) FROM log_entries WHERE author_id IS NOT NULL"
    ) == 0


def test_dev_database_migration_is_idempotent(dev_db_copy: Engine) -> None:
    run_migrations(dev_db_copy)
    run_migrations(dev_db_copy)

    assert _scalar(dev_db_copy, "SELECT COUNT(*) FROM car_members") == SEEDED_CAR_COUNT
    assert _scalar(dev_db_copy, "SELECT COUNT(*) FROM log_entries") == SEEDED_LOG_COUNT
