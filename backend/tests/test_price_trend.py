"""Fuel price history: the chronological series behind the price chart."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.services.stats import PRICE_HISTORY_LIMIT

TODAY = dt.date.today()


def _refuel(
    client: TestClient,
    headers: dict,
    car_id: int,
    odometer: int,
    price_per_liter: float,
    days_ago: int,
    fuel_kind: str | None = None,
    gas_station: str | None = None,
    liters: float = 40.0,
) -> dict:
    refuel: dict = {
        "liters": liters,
        "price_per_liter": price_per_liter,
        "is_full_tank": True,
        "gas_station": gas_station,
    }
    if fuel_kind is not None:
        refuel["fuel_kind"] = fuel_kind
    response = client.post(
        f"/api/cars/{car_id}/logs",
        json={
            "type": "refuel",
            "odometer": odometer,
            "date": (TODAY - dt.timedelta(days=days_ago)).isoformat(),
            "total_cost": round(price_per_liter * liters, 2),
            "refuel": refuel,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _price_history(client: TestClient, headers: dict, car_id: int) -> list[dict]:
    response = client.get(f"/api/cars/{car_id}/analytics", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["price_history"]


def test_empty_car_has_no_price_history(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    assert _price_history(client, auth_headers, car["id"]) == []


def test_car_with_only_non_refuel_logs_has_no_price_history(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    response = client.post(
        f"/api/cars/{car['id']}/logs",
        json={
            "type": "expense",
            "odometer": 10000,
            "date": TODAY.isoformat(),
            "total_cost": 300,
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    assert _price_history(client, auth_headers, car["id"]) == []


def test_price_history_is_oldest_first_regardless_of_entry_order(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """The chart draws left to right, so the series is chronological.

    The refuels are logged newest-first here on purpose: a backdated entry
    must land in its place on the timeline, not at the end of the list.
    """
    car = make_car(current_odometer=10600)
    _refuel(client, auth_headers, car["id"], 10600, 58.10, days_ago=5)
    _refuel(client, auth_headers, car["id"], 10000, 54.90, days_ago=40)
    _refuel(client, auth_headers, car["id"], 10300, 56.50, days_ago=20)

    history = _price_history(client, auth_headers, car["id"])

    assert [item["date"] for item in history] == sorted(item["date"] for item in history)
    assert [item["price_per_liter"] for item in history] == [54.90, 56.50, 58.10]


def test_price_history_item_carries_station_and_kind(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(fuel_type="lpg", current_odometer=10000)
    _refuel(
        client, auth_headers, car["id"], 10000, 26.50,
        days_ago=3, fuel_kind="lpg", gas_station="OKKO",
    )

    history = _price_history(client, auth_headers, car["id"])

    assert len(history) == 1
    assert history[0] == {
        "date": (TODAY - dt.timedelta(days=3)).isoformat(),
        "price_per_liter": 26.50,
        "fuel_kind": "lpg",
        "gas_station": "OKKO",
    }


def test_price_history_kind_resolves_from_the_car_for_legacy_rows(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(fuel_type="diesel", current_odometer=10000)
    _refuel(client, auth_headers, car["id"], 10000, 52.30, days_ago=3)

    history = _price_history(client, auth_headers, car["id"])

    assert history[0]["fuel_kind"] == "diesel"


def test_price_history_keeps_a_missing_station_null(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    _refuel(client, auth_headers, car["id"], 10000, 54.90, days_ago=3)

    assert _price_history(client, auth_headers, car["id"])[0]["gas_station"] is None


def test_lpg_car_keeps_both_kinds_on_one_series(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(fuel_type="lpg", current_odometer=10400)
    _refuel(client, auth_headers, car["id"], 10000, 26.50, days_ago=30, fuel_kind="lpg")
    _refuel(client, auth_headers, car["id"], 10200, 54.90, days_ago=20, fuel_kind="petrol")
    _refuel(client, auth_headers, car["id"], 10400, 27.10, days_ago=10, fuel_kind="lpg")

    history = _price_history(client, auth_headers, car["id"])

    assert [item["fuel_kind"] for item in history] == ["lpg", "petrol", "lpg"]


def test_price_history_is_capped_at_the_hundred_most_recent(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    assert PRICE_HISTORY_LIMIT == 100
    total = PRICE_HISTORY_LIMIT + 5
    car = make_car(current_odometer=10000 + total * 100)
    for index in range(total):
        _refuel(
            client,
            auth_headers,
            car["id"],
            10000 + index * 100,
            50.0 + index,
            days_ago=total - index,
        )

    history = _price_history(client, auth_headers, car["id"])

    assert len(history) == PRICE_HISTORY_LIMIT
    # The five oldest (50.0 .. 54.0) are gone; the newest is still there.
    assert history[0]["price_per_liter"] == pytest.approx(55.0)
    assert history[-1]["price_per_liter"] == pytest.approx(50.0 + total - 1)
