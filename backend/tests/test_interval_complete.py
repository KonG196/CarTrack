"""One-tap interval completion: transactional log + interval advance."""

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.models import Car, LogEntry, ServiceInterval

TODAY = dt.date.today()


def _create_interval(
    client: TestClient, headers: dict, car_id: int, payload: dict
) -> dict:
    response = client.post(
        f"/api/cars/{car_id}/intervals", json=payload, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def _log_count(db_session_factory: sessionmaker) -> int:
    with db_session_factory() as db:
        return db.execute(select(func.count()).select_from(LogEntry)).scalar_one()


def test_complete_creates_one_log_and_advances_interval(
    client: TestClient,
    auth_headers: dict,
    make_car,
    db_session_factory: sessionmaker,
) -> None:
    car = make_car(current_odometer=50000)
    # Due at 49000 km, car is at 50000 km -> overdue by 1000 km before completion.
    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {"title": "Олива двигуна", "interval_km": 10000, "last_odometer": 39000},
    )
    assert interval["status"] == "overdue"

    response = client.post(
        f"/api/intervals/{interval['id']}/complete",
        json={
            "odometer": 50000,
            "date": TODAY.isoformat(),
            "total_cost": 1500,
            "parts_cost": 900,
            "labor_cost": 600,
            "notes": "СТО на Соборній",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()

    log = body["log"]
    assert log["car_id"] == car["id"]
    assert log["type"] == "maintenance"
    assert log["odometer"] == 50000
    assert log["date"] == TODAY.isoformat()
    assert log["total_cost"] == 1500.0
    assert log["notes"] == "СТО на Соборній"
    assert log["maintenance"] == {
        "parts_cost": 900.0,
        "labor_cost": 600.0,
        # items defaults to the interval title
        "items": ["Олива двигуна"],
    }

    advanced = body["interval"]
    assert advanced["id"] == interval["id"]
    assert advanced["last_odometer"] == 50000
    assert advanced["last_date"] == TODAY.isoformat()
    assert advanced["km_left"] == 10000
    assert advanced["status"] == "ok"

    # Exactly one log entry exists for the whole flow.
    assert _log_count(db_session_factory) == 1
    listed = client.get(f"/api/cars/{car['id']}/logs", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1


def test_complete_defaults_items_to_interval_title_and_zero_costs(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=50000)
    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {"title": "Салонний фільтр", "interval_km": 15000, "last_odometer": 40000},
    )
    response = client.post(
        f"/api/intervals/{interval['id']}/complete",
        json={"odometer": 50000, "date": TODAY.isoformat()},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    log = response.json()["log"]
    assert log["total_cost"] == 0.0
    assert log["notes"] is None
    assert log["maintenance"] == {
        "parts_cost": 0.0,
        "labor_cost": 0.0,
        "items": ["Салонний фільтр"],
    }


def test_complete_keeps_explicit_items(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=50000)
    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {"title": "Олива двигуна", "interval_km": 10000, "last_odometer": 40000},
    )
    response = client.post(
        f"/api/intervals/{interval['id']}/complete",
        json={
            "odometer": 50000,
            "date": TODAY.isoformat(),
            "items": ["Олива Motul 5W-30", "Масляний фільтр"],
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["log"]["maintenance"]["items"] == [
        "Олива Motul 5W-30",
        "Масляний фільтр",
    ]


def test_complete_bumps_car_odometer_forward(
    client: TestClient,
    auth_headers: dict,
    make_car,
    db_session_factory: sessionmaker,
) -> None:
    car = make_car(current_odometer=50000)
    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {"title": "Олива двигуна", "interval_km": 10000, "last_odometer": 40000},
    )
    response = client.post(
        f"/api/intervals/{interval['id']}/complete",
        json={"odometer": 60000, "date": TODAY.isoformat()},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    with db_session_factory() as db:
        assert db.get(Car, car["id"]).current_odometer == 60000


def test_complete_clears_last_notified_at(
    client: TestClient,
    auth_headers: dict,
    make_car,
    db_session_factory: sessionmaker,
) -> None:
    car = make_car(current_odometer=50000)
    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {"title": "Олива двигуна", "interval_km": 10000, "last_odometer": 40000},
    )
    with db_session_factory() as db:
        row = db.get(ServiceInterval, interval["id"])
        row.last_notified_at = TODAY
        db.commit()

    response = client.post(
        f"/api/intervals/{interval['id']}/complete",
        json={"odometer": 50000, "date": TODAY.isoformat()},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    with db_session_factory() as db:
        assert db.get(ServiceInterval, interval["id"]).last_notified_at is None


def test_complete_foreign_interval_returns_404(
    client: TestClient,
    auth_headers: dict,
    make_car,
    make_user,
    db_session_factory: sessionmaker,
) -> None:
    car = make_car(current_odometer=50000)
    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {"title": "Олива двигуна", "interval_km": 10000, "last_odometer": 40000},
    )
    other_headers = make_user(email="other@example.com")

    response = client.post(
        f"/api/intervals/{interval['id']}/complete",
        json={"odometer": 50000, "date": TODAY.isoformat()},
        headers=other_headers,
    )
    assert response.status_code == 404
    assert _log_count(db_session_factory) == 0
    with db_session_factory() as db:
        assert db.get(ServiceInterval, interval["id"]).last_odometer == 40000


def test_complete_unknown_interval_returns_404(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.post(
        "/api/intervals/9999/complete",
        json={"odometer": 50000, "date": TODAY.isoformat()},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_complete_requires_auth(client: TestClient, auth_headers: dict, make_car) -> None:
    car = make_car(current_odometer=50000)
    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {"title": "Олива двигуна", "interval_km": 10000, "last_odometer": 40000},
    )
    response = client.post(
        f"/api/intervals/{interval['id']}/complete",
        json={"odometer": 50000, "date": TODAY.isoformat()},
    )
    assert response.status_code == 401


def test_complete_below_car_odometer_does_not_lower_it_but_still_completes(
    client: TestClient,
    auth_headers: dict,
    make_car,
    db_session_factory: sessionmaker,
) -> None:
    car = make_car(current_odometer=50000)
    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {"title": "Олива двигуна", "interval_km": 10000, "last_odometer": 40000},
    )
    response = client.post(
        f"/api/intervals/{interval['id']}/complete",
        json={"odometer": 45000, "date": TODAY.isoformat()},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()

    # The log keeps the odometer the user reported...
    assert body["log"]["odometer"] == 45000
    # ...the interval is completed at that odometer...
    assert body["interval"]["last_odometer"] == 45000
    assert body["interval"]["km_left"] == 5000
    # ...but the car never moves backwards.
    with db_session_factory() as db:
        assert db.get(Car, car["id"]).current_odometer == 50000
    assert _log_count(db_session_factory) == 1


def test_complete_validation_error_creates_nothing(
    client: TestClient,
    auth_headers: dict,
    make_car,
    db_session_factory: sessionmaker,
) -> None:
    car = make_car(current_odometer=50000)
    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {"title": "Олива двигуна", "interval_km": 10000, "last_odometer": 40000},
    )

    invalid_payloads = [
        {"odometer": -1, "date": TODAY.isoformat()},  # negative odometer
        {"odometer": 50000},  # missing date
        {"odometer": 50000, "date": "not-a-date"},
        {"odometer": "багато", "date": TODAY.isoformat()},
        {"odometer": 50000, "date": TODAY.isoformat(), "total_cost": -5},
        {"odometer": 50000, "date": TODAY.isoformat(), "parts_cost": -1},
        {"odometer": 50000, "date": TODAY.isoformat(), "labor_cost": -1},
        {"odometer": 50000, "date": TODAY.isoformat(), "items": "не список"},
    ]
    for payload in invalid_payloads:
        response = client.post(
            f"/api/intervals/{interval['id']}/complete",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code == 422, (payload, response.text)

    # Nothing was written by any of the rejected attempts.
    assert _log_count(db_session_factory) == 0
    with db_session_factory() as db:
        row = db.get(ServiceInterval, interval["id"])
        assert row.last_odometer == 40000
        assert row.last_date is None
        assert db.get(Car, car["id"]).current_odometer == 50000


def test_complete_clears_a_snooze(
    client: TestClient,
    auth_headers: dict,
    make_car,
    db_session_factory: sessionmaker,
) -> None:
    car = make_car(current_odometer=50000)
    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {"title": "Олива двигуна", "interval_km": 10000, "last_odometer": 39000},
    )
    with db_session_factory() as db:
        row = db.get(ServiceInterval, interval["id"])
        row.snoozed_until = TODAY + dt.timedelta(days=5)
        row.last_notified_at = TODAY
        db.commit()

    response = client.post(
        f"/api/intervals/{interval['id']}/complete",
        json={"odometer": 50000, "date": TODAY.isoformat()},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text

    with db_session_factory() as db:
        row = db.get(ServiceInterval, interval["id"])
        assert row.snoozed_until is None
        assert row.last_notified_at is None
