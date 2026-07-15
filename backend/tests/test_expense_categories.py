"""Expense category tests: create/patch defaults, migration 0004, analytics."""

import datetime as dt
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.database import Base
from app.migrations import run_migrations

TODAY = dt.date.today()

DEFAULT_CATEGORY = "Інше"


def _post_expense(
    client: TestClient, headers: dict, car_id: int, **overrides
) -> dict:
    payload = {
        "type": "expense",
        "odometer": 10100,
        "date": TODAY.isoformat(),
        "total_cost": 300,
    }
    payload.update(overrides)
    response = client.post(f"/api/cars/{car_id}/logs", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_expense_with_category(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    body = _post_expense(
        client, auth_headers, car["id"], expense={"category": "Мийка"}
    )
    assert body["expense"] == {"category": "Мийка"}

    fetched = client.get(f"/api/logs/{body['id']}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["expense"]["category"] == "Мийка"


def test_create_expense_without_category_defaults_to_inshe(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    body = _post_expense(client, auth_headers, car["id"])
    assert body["expense"]["category"] == DEFAULT_CATEGORY

    listed = client.get(f"/api/cars/{car['id']}/logs", headers=auth_headers)
    assert listed.json()["items"][0]["expense"]["category"] == DEFAULT_CATEGORY


def test_expense_object_on_other_types_is_not_persisted(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """Only type=expense carries an expense detail row."""
    car = make_car(current_odometer=10000)
    response = client.post(
        f"/api/cars/{car['id']}/logs",
        json={
            "type": "repair",
            "odometer": 10200,
            "date": TODAY.isoformat(),
            "total_cost": 500,
            "repair": {"category": "Підвіска"},
            "expense": {"category": "Мийка"},
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["expense"] is None


def test_create_expense_with_unknown_category_422(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    response = client.post(
        f"/api/cars/{car['id']}/logs",
        json={
            "type": "expense",
            "odometer": 10100,
            "date": TODAY.isoformat(),
            "total_cost": 300,
            "expense": {"category": "Кава"},
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_patch_changes_category(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    created = _post_expense(
        client, auth_headers, car["id"], expense={"category": "Мийка"}
    )

    patched = client.patch(
        f"/api/logs/{created['id']}",
        json={"expense": {"category": "Паркування"}},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["expense"]["category"] == "Паркування"

    fetched = client.get(f"/api/logs/{created['id']}", headers=auth_headers)
    assert fetched.json()["expense"]["category"] == "Паркування"


def _make_legacy_expense(db_session_factory, car_id: int, total_cost: float = 120) -> int:
    import datetime as dt_module

    from app.models import LogEntry

    session = db_session_factory()
    try:
        log = LogEntry(
            car_id=car_id,
            type="expense",
            odometer=10050,
            date=dt_module.date.today(),
            total_cost=total_cost,
            notes="legacy",
        )
        session.add(log)
        session.commit()
        return log.id
    finally:
        session.close()


def test_legacy_expense_serializes_with_the_default_category(
    client: TestClient, auth_headers: dict, make_car, db_session_factory
) -> None:
    """A pre-0004 expense reads as the default category, never as a null detail.

    The row carries no category, but the API must not leak that storage
    detail: analytics already counts it under the default, so the log
    endpoints report the same bucket rather than a null the client would
    have to special-case.
    """
    car = make_car(current_odometer=10000)
    log_id = _make_legacy_expense(db_session_factory, car["id"])

    fetched = client.get(f"/api/logs/{log_id}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["expense"] == {"category": DEFAULT_CATEGORY}

    listed = client.get(f"/api/cars/{car['id']}/logs", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["expense"] == {"category": DEFAULT_CATEGORY}


def test_legacy_expense_default_category_is_not_written_back(
    client: TestClient, auth_headers: dict, make_car, db_session_factory
) -> None:
    """Reading a legacy expense stays a read: no category row is back-filled."""
    car = make_car(current_odometer=10000)
    log_id = _make_legacy_expense(db_session_factory, car["id"])

    assert client.get(f"/api/logs/{log_id}", headers=auth_headers).status_code == 200

    session = db_session_factory()
    try:
        rows = session.execute(
            text("SELECT COUNT(*) FROM expense_details WHERE log_entry_id = :id"),
            {"id": log_id},
        ).scalar_one()
    finally:
        session.close()
    assert rows == 0


def test_patch_adds_category_to_a_legacy_expense(
    client: TestClient, auth_headers: dict, make_car, db_session_factory
) -> None:
    car = make_car(current_odometer=10000)
    log_id = _make_legacy_expense(db_session_factory, car["id"])

    fetched = client.get(f"/api/logs/{log_id}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["expense"] == {"category": DEFAULT_CATEGORY}

    patched = client.patch(
        f"/api/logs/{log_id}",
        json={"expense": {"category": "Штраф"}},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["expense"]["category"] == "Штраф"

    # The patch persisted a real row, not the read-time default.
    assert (
        client.get(f"/api/logs/{log_id}", headers=auth_headers).json()["expense"][
            "category"
        ]
        == "Штраф"
    )


def test_type_change_away_from_expense_drops_the_category(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    created = _post_expense(
        client, auth_headers, car["id"], expense={"category": "Мийка"}
    )
    patched = client.patch(
        f"/api/logs/{created['id']}",
        json={"type": "repair", "repair": {"category": "Підвіска"}},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["expense"] is None


def test_analytics_expense_by_category(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    _post_expense(
        client, auth_headers, car["id"], total_cost=300, expense={"category": "Мийка"}
    )
    _post_expense(
        client,
        auth_headers,
        car["id"],
        odometer=10200,
        total_cost=200,
        expense={"category": "Мийка"},
    )
    _post_expense(
        client,
        auth_headers,
        car["id"],
        odometer=10300,
        total_cost=50,
        expense={"category": "Паркування"},
    )
    # No expense object: falls into the default category.
    _post_expense(client, auth_headers, car["id"], odometer=10400, total_cost=25)
    # A non-expense log must not appear in the breakdown.
    response = client.post(
        f"/api/cars/{car['id']}/logs",
        json={
            "type": "refuel",
            "odometer": 10500,
            "date": TODAY.isoformat(),
            "total_cost": 1000,
            "refuel": {"liters": 40, "price_per_liter": 25, "is_full_tank": True},
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text

    body = client.get(f"/api/cars/{car['id']}/analytics", headers=auth_headers).json()
    assert body["expense_by_category"] == {
        "Мийка": 500.0,
        "Паркування": 50.0,
        DEFAULT_CATEGORY: 25.0,
    }
    # totals.by_type is unchanged by the breakdown.
    assert body["totals"]["by_type"]["expense"] == 575.0
    assert sum(body["expense_by_category"].values()) == body["totals"]["by_type"]["expense"]


def test_analytics_expense_by_category_is_empty_without_expenses(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    body = client.get(f"/api/cars/{car['id']}/analytics", headers=auth_headers).json()
    assert body["expense_by_category"] == {}


@pytest.fixture()
def file_engine(tmp_path) -> Generator[Engine, None, None]:
    engine = create_engine(f"sqlite:///{tmp_path / 'expense.db'}")
    yield engine
    engine.dispose()


def test_migration_0004_keeps_legacy_rows(file_engine: Engine) -> None:
    # A legacy database: current schema minus the new table, with real rows.
    Base.metadata.create_all(bind=file_engine)
    with file_engine.begin() as connection:
        connection.execute(text("DROP TABLE expense_details"))
        connection.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, created_at) "
                "VALUES (1, 'legacy@example.com', 'x', '2026-01-01 00:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO cars (id, user_id, brand, model, year, fuel_type, "
                "current_odometer, created_at) "
                "VALUES (1, 1, 'Toyota', 'Corolla', 2018, 'petrol', 10000, "
                "'2026-01-01 00:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO log_entries (id, car_id, type, odometer, date, "
                "total_cost, notes, created_at) "
                "VALUES (1, 1, 'expense', 10100, '2026-01-02', 300, 'мийка', "
                "'2026-01-02 00:00:00')"
            )
        )
    assert "expense_details" not in inspect(file_engine).get_table_names()

    run_migrations(file_engine)

    assert "expense_details" in inspect(file_engine).get_table_names()
    columns = {col["name"] for col in inspect(file_engine).get_columns("expense_details")}
    assert columns == {"log_entry_id", "category"}
    with file_engine.connect() as connection:
        assert (
            connection.execute(text("SELECT COUNT(*) FROM log_entries")).scalar_one() == 1
        )
        assert (
            connection.execute(
                text("SELECT notes FROM log_entries WHERE id = 1")
            ).scalar_one()
            == "мийка"
        )
        # Legacy rows get no back-filled category.
        assert (
            connection.execute(text("SELECT COUNT(*) FROM expense_details")).scalar_one()
            == 0
        )


def test_migration_0004_is_idempotent(file_engine: Engine) -> None:
    run_migrations(file_engine)
    run_migrations(file_engine)  # a second run must be a no-op, not a crash
    assert "expense_details" in inspect(file_engine).get_table_names()


def test_deleting_a_log_cascades_to_its_category(
    client: TestClient, auth_headers: dict, make_car, db_session_factory
) -> None:
    car = make_car(current_odometer=10000)
    created = _post_expense(
        client, auth_headers, car["id"], expense={"category": "Шини"}
    )
    assert client.delete(f"/api/logs/{created['id']}", headers=auth_headers).status_code == 204

    session = db_session_factory()
    try:
        remaining = session.execute(
            text("SELECT COUNT(*) FROM expense_details WHERE log_entry_id = :id"),
            {"id": created["id"]},
        ).scalar_one()
    finally:
        session.close()
    assert remaining == 0
