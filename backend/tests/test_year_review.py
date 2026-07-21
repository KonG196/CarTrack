"""«Ваш рік з Kapot» — the one-year recap endpoint."""

from fastapi.testclient import TestClient


def _add_log(client: TestClient, headers: dict, car_id: int, payload: dict) -> None:
    response = client.post(f"/api/cars/{car_id}/logs", json=payload, headers=headers)
    assert response.status_code == 201, response.text


def test_year_review_aggregates_the_year(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=100000)
    cid = car["id"]
    _add_log(client, auth_headers, cid, {
        "type": "refuel", "odometer": 100200, "date": "2026-02-10", "total_cost": 3000,
        "refuel": {"liters": 55, "price_per_liter": 54.5, "is_full_tank": True, "gas_station": "OKKO"},
    })
    _add_log(client, auth_headers, cid, {
        "type": "refuel", "odometer": 100700, "date": "2026-03-15", "total_cost": 2900,
        "refuel": {"liters": 52, "price_per_liter": 55.8, "is_full_tank": True, "gas_station": "WOG"},
    })
    _add_log(client, auth_headers, cid, {
        "type": "repair", "odometer": 100900, "date": "2026-04-01", "total_cost": 15000,
        "repair": {"category": "Двигун"},
    })
    # a second April entry makes April the most-active month (2 entries)
    _add_log(client, auth_headers, cid, {
        "type": "expense", "odometer": 100900, "date": "2026-04-20", "total_cost": 300,
        "expense": {"category": "Мийка"},
    })

    body = client.get(f"/api/cars/{cid}/year-review?year=2026", headers=auth_headers).json()
    assert body["has_data"] is True
    assert body["year"] == 2026
    assert 2026 in body["available_years"]
    assert body["total_spent"] == 21200.0
    assert body["refuels_count"] == 2
    assert body["km_driven"] == 700  # 100900 - 100200
    assert body["biggest_expense"]["type"] == "repair"
    assert body["biggest_expense"]["amount"] == 15000.0
    assert body["cheapest_station"]["name"] == "OKKO"  # 54.5 < 55.77 ₴/л
    assert body["busiest_month"] == 4  # April has 2 entries (repair + wash)


def test_zero_odometer_prefill_does_not_corrupt_km(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    # A first log saved at the prefilled odometer 0 must not blow km_driven up.
    car = make_car(current_odometer=0)
    cid = car["id"]
    _add_log(client, auth_headers, cid, {
        "type": "expense", "odometer": 0, "date": "2026-01-05", "total_cost": 100,
        "expense": {"category": "Мийка"},
    })
    _add_log(client, auth_headers, cid, {
        "type": "refuel", "odometer": 100200, "date": "2026-02-10", "total_cost": 3000,
        "refuel": {"liters": 55, "price_per_liter": 54.5, "is_full_tank": True, "gas_station": "OKKO"},
    })
    _add_log(client, auth_headers, cid, {
        "type": "refuel", "odometer": 100900, "date": "2026-03-15", "total_cost": 2900,
        "refuel": {"liters": 52, "price_per_liter": 55.8, "is_full_tank": True, "gas_station": "WOG"},
    })
    body = client.get(f"/api/cars/{cid}/year-review?year=2026", headers=auth_headers).json()
    assert body["km_driven"] == 700  # 100900 - 100200, not 100900 - 0


def test_year_review_empty_year(client: TestClient, auth_headers: dict, make_car) -> None:
    car = make_car(current_odometer=100000)
    body = client.get(f"/api/cars/{car['id']}/year-review?year=2020", headers=auth_headers).json()
    assert body["has_data"] is False
    assert body["total_spent"] is None


def test_year_review_defaults_to_latest_year(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=100000)
    _add_log(client, auth_headers, car["id"], {
        "type": "expense", "odometer": 100100, "date": "2025-06-01", "total_cost": 500,
        "expense": {"category": "Мийка"},
    })
    body = client.get(f"/api/cars/{car['id']}/year-review", headers=auth_headers).json()
    assert body["year"] == 2025
    assert body["has_data"] is True
