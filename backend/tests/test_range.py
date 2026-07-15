"""Tank volume and the full-tank range estimate.

The estimate answers «how far does a full tank go at this car's measured
consumption», NOT «how much is left» — nothing in the app knows the current
tank level, so every assertion here is about the full-tank number.
"""

import datetime as dt

from fastapi.testclient import TestClient

from app.services.fuel import compute_range_km

TODAY = dt.date.today()


def _post_log(client: TestClient, headers: dict, car_id: int, payload: dict) -> None:
    response = client.post(f"/api/cars/{car_id}/logs", json=payload, headers=headers)
    assert response.status_code == 201, response.text


def _refuel(
    client: TestClient, headers: dict, car_id: int, odometer: int, liters: float
) -> None:
    _post_log(
        client,
        headers,
        car_id,
        {
            "type": "refuel",
            "odometer": odometer,
            "date": TODAY.isoformat(),
            "total_cost": liters * 50,
            "refuel": {"liters": liters, "price_per_liter": 50, "is_full_tank": True},
        },
    )


# The math (app.services.fuel.compute_range_km)


def test_range_is_the_tank_divided_by_the_consumption_per_100km() -> None:
    # 50 л at 6.25 л/100км -> 800 км exactly.
    assert compute_range_km(50.0, 6.25) == 800
    assert compute_range_km(50.0, 8.0) == 630


def test_range_rounds_half_up_to_the_nearest_10_km() -> None:
    # 625 km sits exactly on a half-step. Python's round() is banker's and
    # would answer 620 here, which reads as an arbitrary loss of 10 km.
    assert compute_range_km(50.0, 8.0) == 630
    assert compute_range_km(50.0, 8.1) == 620  # 617.28 -> 620
    assert compute_range_km(50.0, 6.0) == 830  # 833.33 -> 830


def test_range_is_unknown_without_a_tank_volume() -> None:
    assert compute_range_km(None, 6.0) is None


def test_range_is_unknown_without_a_measured_consumption() -> None:
    assert compute_range_km(50.0, None) is None


def test_range_is_unknown_for_a_non_positive_input() -> None:
    """Neither value can be zero through the API, but the math must not divide by it."""
    assert compute_range_km(0.0, 6.0) is None
    assert compute_range_km(50.0, 0.0) is None
    assert compute_range_km(-50.0, 6.0) is None


# The car field


def test_car_tank_liters_defaults_to_null(make_car) -> None:
    assert make_car()["tank_liters"] is None


def test_car_stores_and_clears_tank_liters(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(tank_liters=50)
    assert car["tank_liters"] == 50.0

    patched = client.patch(
        f"/api/cars/{car['id']}", json={"tank_liters": 55.5}, headers=auth_headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["tank_liters"] == 55.5

    cleared = client.patch(
        f"/api/cars/{car['id']}", json={"tank_liters": None}, headers=auth_headers
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["tank_liters"] is None


def test_car_rejects_a_non_positive_tank_422(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    for bad in (0, -50):
        response = client.patch(
            f"/api/cars/{car['id']}", json={"tank_liters": bad}, headers=auth_headers
        )
        assert response.status_code == 422, f"{bad}: {response.text}"


# analytics.range_km


def test_analytics_range_is_null_without_a_tank(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    _refuel(client, auth_headers, car["id"], 10000, 45)
    _refuel(client, auth_headers, car["id"], 10500, 40)

    body = client.get(f"/api/cars/{car['id']}/analytics", headers=auth_headers).json()
    assert body["fuel"]["avg_consumption_l_100km"] == 8.0
    assert body["range_km"] is None


def test_analytics_range_is_null_without_a_measured_consumption(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000, tank_liters=50)
    body = client.get(f"/api/cars/{car['id']}/analytics", headers=auth_headers).json()
    assert body["fuel"]["avg_consumption_l_100km"] is None
    assert body["range_km"] is None


def test_analytics_range_from_the_tank_and_the_measured_consumption(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000, tank_liters=50)
    _refuel(client, auth_headers, car["id"], 10000, 45)  # anchor
    _refuel(client, auth_headers, car["id"], 10500, 40)  # 40 л / 500 км = 8 л/100км

    body = client.get(f"/api/cars/{car['id']}/analytics", headers=auth_headers).json()
    assert body["fuel"]["avg_consumption_l_100km"] == 8.0
    assert body["range_km"] == 630  # 50 / 8 * 100 = 625 -> 630


def test_analytics_range_follows_the_tank_being_edited(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000, tank_liters=50)
    _refuel(client, auth_headers, car["id"], 10000, 45)
    _refuel(client, auth_headers, car["id"], 10500, 40)

    client.patch(f"/api/cars/{car['id']}", json={"tank_liters": 60}, headers=auth_headers)
    body = client.get(f"/api/cars/{car['id']}/analytics", headers=auth_headers).json()
    assert body["range_km"] == 750  # 60 / 8 * 100
