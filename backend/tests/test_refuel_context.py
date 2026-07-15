"""Refuel form context: recent stations, last price and odometer anchors."""

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import event

TODAY = dt.date.today()


def _refuel(
    client: TestClient,
    headers: dict,
    car_id: int,
    odometer: int,
    days_ago: int,
    price_per_liter: float = 55.0,
    gas_station: str | None = "WOG",
) -> dict:
    payload = {
        "type": "refuel",
        "odometer": odometer,
        "date": (TODAY - dt.timedelta(days=days_ago)).isoformat(),
        "total_cost": round(40 * price_per_liter, 2),
        "refuel": {
            "liters": 40,
            "price_per_liter": price_per_liter,
            "is_full_tank": True,
            "gas_station": gas_station,
        },
    }
    response = client.post(f"/api/cars/{car_id}/logs", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _context(client: TestClient, headers: dict, car_id: int) -> dict:
    response = client.get(f"/api/cars/{car_id}/refuel-context", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_empty_car_returns_nulls_and_no_stations(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    body = _context(client, auth_headers, car["id"])
    assert body == {
        "recent_stations": [],
        "last_price_per_liter": None,
        "last_refuel_odometer": None,
        "last_entry_odometer": None,
        "last_entry_date": None,
    }


def test_recent_stations_are_distinct_recent_first_and_capped_at_five(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    # Oldest first; "WOG" repeats so only its most recent position must count.
    seeded = [
        (6, "UPG"),
        (5, "WOG"),
        (4, "OKKO"),
        (3, "SOCAR"),
        (2, "Shell"),
        (1, "WOG"),
        (0, "Amic"),
    ]
    for index, (days_ago, station) in enumerate(seeded):
        _refuel(
            client,
            auth_headers,
            car["id"],
            odometer=10000 + index * 400,
            days_ago=days_ago,
            gas_station=station,
        )

    body = _context(client, auth_headers, car["id"])
    assert body["recent_stations"] == ["Amic", "WOG", "Shell", "SOCAR", "OKKO"]


def test_last_price_and_odometers_come_from_the_right_entries(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    _refuel(client, auth_headers, car["id"], odometer=10400, days_ago=5, price_per_liter=52.5)
    _refuel(client, auth_headers, car["id"], odometer=10800, days_ago=2, price_per_liter=57.25)
    # A later non-refuel entry drives last_entry_*, never the refuel anchors.
    response = client.post(
        f"/api/cars/{car['id']}/logs",
        json={
            "type": "expense",
            "odometer": 11200,
            "date": TODAY.isoformat(),
            "total_cost": 300,
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text

    body = _context(client, auth_headers, car["id"])
    assert body["last_price_per_liter"] == 57.25
    assert body["last_refuel_odometer"] == 10800
    assert body["last_entry_odometer"] == 11200
    assert body["last_entry_date"] == TODAY.isoformat()


def test_last_entry_odometer_is_the_maximum_across_all_logs(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """A backdated correction must not pull the odometer anchor down."""
    car = make_car(current_odometer=10000)
    _refuel(client, auth_headers, car["id"], odometer=20000, days_ago=10)
    _refuel(client, auth_headers, car["id"], odometer=12000, days_ago=1)

    body = _context(client, auth_headers, car["id"])
    assert body["last_entry_odometer"] == 20000
    assert body["last_refuel_odometer"] == 12000
    assert body["last_entry_date"] == (TODAY - dt.timedelta(days=1)).isoformat()


def test_stations_omit_blank_values(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    _refuel(client, auth_headers, car["id"], odometer=10400, days_ago=3, gas_station="OKKO")
    _refuel(client, auth_headers, car["id"], odometer=10800, days_ago=2, gas_station=None)
    _refuel(client, auth_headers, car["id"], odometer=11200, days_ago=1, gas_station="   ")

    body = _context(client, auth_headers, car["id"])
    assert body["recent_stations"] == ["OKKO"]
    assert body["last_refuel_odometer"] == 11200


def test_car_without_refuels_still_reports_entry_anchors(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    response = client.post(
        f"/api/cars/{car['id']}/logs",
        json={
            "type": "expense",
            "odometer": 10500,
            "date": TODAY.isoformat(),
            "total_cost": 120,
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text

    body = _context(client, auth_headers, car["id"])
    assert body["recent_stations"] == []
    assert body["last_price_per_liter"] is None
    assert body["last_refuel_odometer"] is None
    assert body["last_entry_odometer"] == 10500
    assert body["last_entry_date"] == TODAY.isoformat()


def test_refuel_context_requires_ownership(
    client: TestClient, make_car, make_user
) -> None:
    car = make_car()
    other_headers = make_user(email="other@example.com")
    response = client.get(f"/api/cars/{car['id']}/refuel-context", headers=other_headers)
    assert response.status_code == 404


def test_refuel_context_requires_auth(client: TestClient, make_car) -> None:
    car = make_car()
    assert client.get(f"/api/cars/{car['id']}/refuel-context").status_code == 401


def test_refuel_context_query_count_does_not_scale_with_logs(
    client: TestClient, auth_headers: dict, make_car, db_engine
) -> None:
    """The context is one aggregate read, never a query per refuel."""
    counts: list[int] = []
    for n_logs in (2, 12):
        car = make_car(current_odometer=30000)
        for i in range(n_logs):
            _refuel(
                client,
                auth_headers,
                car["id"],
                odometer=10000 + i * 400,
                days_ago=n_logs - i,
                gas_station=f"Station {i}",
            )

        statements: list[str] = []

        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(db_engine, "before_cursor_execute", before_cursor_execute)
        try:
            response = client.get(
                f"/api/cars/{car['id']}/refuel-context", headers=auth_headers
            )
        finally:
            event.remove(db_engine, "before_cursor_execute", before_cursor_execute)
        assert response.status_code == 200
        counts.append(len(statements))

    assert counts[0] == counts[1], f"query count grew with log count: {counts}"
