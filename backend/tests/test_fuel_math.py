"""Full-to-full fuel consumption math tests (via the analytics endpoint)."""

import datetime as dt

from fastapi.testclient import TestClient

TODAY = dt.date.today()


def _refuel(
    client: TestClient,
    headers: dict,
    car_id: int,
    odometer: int,
    liters: float,
    is_full_tank: bool,
    total_cost: float,
    days_ago: int,
) -> None:
    response = client.post(
        f"/api/cars/{car_id}/logs",
        json={
            "type": "refuel",
            "odometer": odometer,
            "date": (TODAY - dt.timedelta(days=days_ago)).isoformat(),
            "total_cost": total_cost,
            "refuel": {
                "liters": liters,
                "price_per_liter": round(total_cost / liters, 2),
                "is_full_tank": is_full_tank,
            },
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text


def _fuel(client: TestClient, headers: dict, car_id: int) -> dict:
    response = client.get(f"/api/cars/{car_id}/analytics", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["fuel"]


def test_full_partial_full_segment(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    _refuel(client, auth_headers, car["id"], 10000, 40, True, 60.0, days_ago=30)
    _refuel(client, auth_headers, car["id"], 10400, 20, False, 30.0, days_ago=20)
    _refuel(client, auth_headers, car["id"], 10800, 25, True, 37.5, days_ago=10)

    fuel = _fuel(client, auth_headers, car["id"])
    assert len(fuel["history"]) == 1
    segment = fuel["history"][0]
    assert segment["odometer"] == 10800
    assert segment["distance_km"] == 800
    assert abs(segment["liters"] - 45.0) < 0.01
    assert abs(segment["consumption_l_100km"] - 5.625) <= 0.02

    assert abs(fuel["avg_consumption_l_100km"] - 5.625) <= 0.02
    assert abs(fuel["last_consumption_l_100km"] - 5.625) <= 0.02
    # (30.0 + 37.5) spent over 800 measured km
    assert abs(fuel["avg_cost_per_km"] - 0.084375) < 0.001


def test_no_full_tank_anchor_yields_no_history(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    _refuel(client, auth_headers, car["id"], 10100, 15, False, 22.5, days_ago=5)
    _refuel(client, auth_headers, car["id"], 10300, 18, False, 27.0, days_ago=2)

    fuel = _fuel(client, auth_headers, car["id"])
    assert fuel["history"] == []
    assert fuel["avg_consumption_l_100km"] is None
    assert fuel["last_consumption_l_100km"] is None
    assert fuel["avg_cost_per_km"] is None


def test_partial_before_first_full_is_discarded(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    _refuel(client, auth_headers, car["id"], 10000, 10, False, 15.0, days_ago=30)
    _refuel(client, auth_headers, car["id"], 10300, 35, True, 52.5, days_ago=20)
    _refuel(client, auth_headers, car["id"], 10700, 20, True, 30.0, days_ago=10)

    fuel = _fuel(client, auth_headers, car["id"])
    # Only the 10300 -> 10700 segment is measurable: 20 L / 400 km = 5.0
    assert len(fuel["history"]) == 1
    segment = fuel["history"][0]
    assert segment["distance_km"] == 400
    assert abs(segment["liters"] - 20.0) < 0.01
    assert abs(segment["consumption_l_100km"] - 5.0) <= 0.02


def test_zero_distance_segment_is_skipped(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    _refuel(client, auth_headers, car["id"], 10000, 30, True, 45.0, days_ago=10)
    # Same odometer full tank: zero distance -> skipped, becomes new anchor.
    _refuel(client, auth_headers, car["id"], 10000, 5, True, 7.5, days_ago=9)
    _refuel(client, auth_headers, car["id"], 10500, 25, True, 37.5, days_ago=1)

    fuel = _fuel(client, auth_headers, car["id"])
    assert len(fuel["history"]) == 1
    segment = fuel["history"][0]
    assert segment["distance_km"] == 500
    assert abs(segment["consumption_l_100km"] - 5.0) <= 0.02
