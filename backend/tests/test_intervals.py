"""Service interval status engine tests: ok / due_soon / overdue and CRUD."""

import datetime as dt

from fastapi.testclient import TestClient

TODAY = dt.date.today()


def _create_interval(
    client: TestClient, headers: dict, car_id: int, payload: dict
) -> dict:
    response = client.post(
        f"/api/cars/{car_id}/intervals", json=payload, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_interval_ok_km_based(client: TestClient, auth_headers: dict, make_car) -> None:
    car = make_car(current_odometer=50000)
    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {"title": "Oil change", "interval_km": 10000, "last_odometer": 45000},
    )
    assert interval["due_odometer"] == 55000
    assert interval["km_left"] == 5000
    assert interval["due_date"] is None
    assert interval["days_left"] is None
    assert interval["health_pct"] == 50.0
    assert interval["status"] == "ok"
    # avg_daily_km defaults to 40 -> 5000 km / 40 = 125 days out
    assert interval["predicted_due_date"] == (TODAY + dt.timedelta(days=125)).isoformat()


def test_interval_due_soon_km_based(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=50000)
    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {"title": "Air filter", "interval_km": 10000, "last_odometer": 40500},
    )
    assert interval["km_left"] == 500
    assert interval["status"] == "due_soon"
    assert interval["health_pct"] == 5.0


def test_interval_overdue_km_based(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=50000)
    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {"title": "Timing belt", "interval_km": 10000, "last_odometer": 39000},
    )
    assert interval["km_left"] == -1000
    assert interval["status"] == "overdue"
    assert interval["health_pct"] == 0.0


def test_interval_overdue_days_based(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=50000)
    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {
            "title": "Insurance",
            "interval_days": 30,
            "last_date": (TODAY - dt.timedelta(days=40)).isoformat(),
        },
    )
    assert interval["due_date"] == (TODAY - dt.timedelta(days=10)).isoformat()
    assert interval["days_left"] == -10
    assert interval["status"] == "overdue"
    assert interval["health_pct"] == 0.0
    assert interval["km_left"] is None


def test_interval_due_soon_days_based(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=50000)
    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {
            "title": "Inspection",
            "interval_days": 30,
            "last_date": (TODAY - dt.timedelta(days=20)).isoformat(),
        },
    )
    assert interval["days_left"] == 10
    # 10/30 remaining ≈ 33% health but days_left < 14 forces due_soon
    assert interval["health_pct"] > 15.0
    assert interval["status"] == "due_soon"


def test_interval_combined_km_and_days_uses_tighter_fraction(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=50000)
    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {
            "title": "Full service",
            "interval_km": 10000,
            "interval_days": 365,
            "last_odometer": 45000,
            "last_date": (TODAY - dt.timedelta(days=100)).isoformat(),
        },
    )
    # km fraction 0.5 vs days fraction ~0.73 -> health from km side
    assert interval["health_pct"] == 50.0
    assert interval["status"] == "ok"
    # km projection (today + 125d) is sooner than the calendar due date (+265d)
    assert interval["predicted_due_date"] == (TODAY + dt.timedelta(days=125)).isoformat()


def test_interval_without_any_limit_422(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    response = client.post(
        f"/api/cars/{car['id']}/intervals",
        json={"title": "Broken", "last_odometer": 1000},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_interval_without_anchor_has_null_derived_fields(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=50000)
    interval = _create_interval(
        client, auth_headers, car["id"], {"title": "Coolant", "interval_km": 60000}
    )
    assert interval["due_odometer"] is None
    assert interval["km_left"] is None
    assert interval["predicted_due_date"] is None
    assert interval["health_pct"] == 100.0
    assert interval["status"] == "ok"


def test_interval_prediction_with_tiny_avg_daily_km_does_not_overflow(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """A near-zero average daily pace must not crash the prediction.

    Two logs 730 days apart with a 1 km odometer delta give
    avg_daily_km ~ 0.00137; projecting 50000 km at that pace lands far
    beyond datetime.date.max. The endpoint must return 200 with no
    km-based prediction instead of raising OverflowError (HTTP 500).
    """
    car = make_car(current_odometer=10001)
    for days_ago, odometer in ((730, 10000), (0, 10001)):
        response = client.post(
            f"/api/cars/{car['id']}/logs",
            json={
                "type": "expense",
                "odometer": odometer,
                "date": (TODAY - dt.timedelta(days=days_ago)).isoformat(),
                "total_cost": 5,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text

    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {"title": "Timing belt", "interval_km": 50000, "last_odometer": 10001},
    )
    assert interval["km_left"] == 50000
    assert interval["predicted_due_date"] is None
    assert interval["health_pct"] == 100.0
    assert interval["status"] == "ok"

    listed = client.get(f"/api/cars/{car['id']}/intervals", headers=auth_headers)
    assert listed.status_code == 200, listed.text

    # A calendar due date still wins when the km projection overflows.
    combined = _create_interval(
        client,
        auth_headers,
        car["id"],
        {
            "title": "Inspection",
            "interval_km": 50000,
            "interval_days": 365,
            "last_odometer": 10001,
            "last_date": TODAY.isoformat(),
        },
    )
    assert combined["predicted_due_date"] == (TODAY + dt.timedelta(days=365)).isoformat()


def test_interval_patch_and_delete(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=50000)
    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {"title": "Oil change", "interval_km": 10000, "last_odometer": 45000},
    )

    patched = client.patch(
        f"/api/intervals/{interval['id']}",
        json={"title": "Oil + filter change", "last_odometer": 49000},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["title"] == "Oil + filter change"
    assert body["due_odometer"] == 59000
    assert body["km_left"] == 9000

    listed = client.get(f"/api/cars/{car['id']}/intervals", headers=auth_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    deleted = client.delete(f"/api/intervals/{interval['id']}", headers=auth_headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/cars/{car['id']}/intervals", headers=auth_headers).json() == []


def test_interval_ownership_isolation(
    client: TestClient, auth_headers: dict, make_car, make_user
) -> None:
    car = make_car()
    interval = _create_interval(
        client, auth_headers, car["id"], {"title": "Oil", "interval_km": 10000}
    )
    other_headers = make_user(email="other@example.com")

    assert (
        client.get(f"/api/cars/{car['id']}/intervals", headers=other_headers).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/cars/{car['id']}/intervals",
            json={"title": "X", "interval_km": 1000},
            headers=other_headers,
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/intervals/{interval['id']}",
            json={"title": "Hacked"},
            headers=other_headers,
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/intervals/{interval['id']}", headers=other_headers).status_code
        == 404
    )
