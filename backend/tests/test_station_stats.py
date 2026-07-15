"""Per-station refuel analytics: grouping, canonical naming and ordering."""

import datetime as dt

from fastapi.testclient import TestClient

from app.services.stats import compute_station_stats

TODAY = dt.date.today()


def _refuel(
    client: TestClient,
    headers: dict,
    car_id: int,
    odometer: int,
    liters: float,
    is_full_tank: bool,
    days_ago: int,
    total_cost: float = 100.0,
    gas_station: str | None = None,
) -> dict:
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
                "gas_station": gas_station,
            },
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _stations(client: TestClient, headers: dict, car_id: int) -> list[dict]:
    response = client.get(f"/api/cars/{car_id}/analytics", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["stations"]


# Grouping and canonical naming


def test_grouping_is_case_insensitive_and_keeps_the_most_used_spelling(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    _refuel(client, auth_headers, car["id"], 10000, 40, True, 30, gas_station="OKKO")
    _refuel(client, auth_headers, car["id"], 10500, 40, True, 20, gas_station="OKKO")
    _refuel(client, auth_headers, car["id"], 11000, 40, True, 10, gas_station="okko")

    stations = _stations(client, auth_headers, car["id"])
    assert len(stations) == 1
    assert stations[0]["name"] == "OKKO"
    assert stations[0]["refuels"] == 3


def test_canonical_name_breaks_ties_deterministically(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    _refuel(client, auth_headers, car["id"], 10000, 40, True, 30, gas_station="WOG")
    _refuel(client, auth_headers, car["id"], 10500, 40, True, 20, gas_station="wog")

    stations = _stations(client, auth_headers, car["id"])
    assert len(stations) == 1
    assert stations[0]["name"] == "WOG"


def test_blank_and_missing_stations_collapse_into_one_unnamed_bucket(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """null, '' and whitespace-only station names share the «Без назви» bucket."""
    car = make_car()
    _refuel(client, auth_headers, car["id"], 10000, 40, True, 30, gas_station=None)
    _refuel(client, auth_headers, car["id"], 10500, 40, True, 20, gas_station="")
    _refuel(client, auth_headers, car["id"], 11000, 40, True, 10, gas_station="   ")

    stations = _stations(client, auth_headers, car["id"])
    assert len(stations) == 1
    assert stations[0]["name"] == "Без назви"
    assert stations[0]["refuels"] == 3


# Aggregates and ordering


def test_stations_are_sorted_by_total_cost_desc_with_correct_aggregates(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    # Cheap station: one 40 L / 400 UAH fill.
    _refuel(
        client, auth_headers, car["id"], 10000, 40, True, 40,
        total_cost=400.0, gas_station="ANP",
    )
    # Expensive station: two fills, 1500 UAH total.
    _refuel(
        client, auth_headers, car["id"], 10500, 50, True, 30,
        total_cost=1000.0, gas_station="OKKO",
    )
    _refuel(
        client, auth_headers, car["id"], 11000, 25, True, 20,
        total_cost=500.0, gas_station="OKKO",
    )

    stations = _stations(client, auth_headers, car["id"])
    assert [station["name"] for station in stations] == ["OKKO", "ANP"]

    okko = stations[0]
    assert okko["refuels"] == 2
    assert okko["total_liters"] == 75.0
    assert okko["total_cost"] == 1500.0
    # 1500 UAH / 75 L — the blended price actually paid, not a mean of means.
    assert okko["avg_price_per_liter"] == 20.0


# Consumption attribution: segments STARTING at a station


def test_consumption_is_attributed_to_the_station_the_segment_starts_at(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """A full-to-full segment counts for the station where the tank was filled.

    OKKO(10000, full) -> WOG(10500, full 40 L): the 40 L burned over those
    500 km were bought AT OKKO, so the 8.0 L/100km lands on OKKO. WOG only
    anchors a segment that never closes, so it has no measurable consumption.
    """
    car = make_car()
    _refuel(client, auth_headers, car["id"], 10000, 40, True, 30, gas_station="OKKO")
    _refuel(client, auth_headers, car["id"], 10500, 40, True, 20, gas_station="WOG")

    stations = {s["name"]: s for s in _stations(client, auth_headers, car["id"])}
    assert stations["OKKO"]["avg_consumption_l_100km"] == 8.0
    assert stations["WOG"]["avg_consumption_l_100km"] is None


def test_station_consumption_averages_all_of_its_segments(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    # OKKO -> WOG: 40 L / 500 km = 8.0
    _refuel(client, auth_headers, car["id"], 10000, 40, True, 40, gas_station="OKKO")
    _refuel(client, auth_headers, car["id"], 10500, 40, True, 30, gas_station="WOG")
    # OKKO -> WOG: 50 L / 500 km = 10.0
    _refuel(client, auth_headers, car["id"], 11000, 50, True, 20, gas_station="OKKO")
    _refuel(client, auth_headers, car["id"], 11500, 50, True, 10, gas_station="WOG")

    stations = {s["name"]: s for s in _stations(client, auth_headers, car["id"])}
    # Segments start at OKKO(10000) and OKKO(11000): mean(8.0, 10.0).
    assert stations["OKKO"]["avg_consumption_l_100km"] == 9.0


def test_partial_refuel_station_has_no_consumption_but_still_counts_money(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """A station only ever used for partial fills reports null consumption."""
    car = make_car()
    _refuel(client, auth_headers, car["id"], 10000, 40, True, 30, gas_station="OKKO")
    _refuel(
        client, auth_headers, car["id"], 10200, 10, False, 25,
        total_cost=300.0, gas_station="ANP",
    )
    _refuel(client, auth_headers, car["id"], 10500, 30, True, 20, gas_station="WOG")

    stations = {s["name"]: s for s in _stations(client, auth_headers, car["id"])}
    assert stations["ANP"]["avg_consumption_l_100km"] is None
    assert stations["ANP"]["total_cost"] == 300.0
    assert stations["ANP"]["refuels"] == 1


# Edge cases


def test_car_without_refuels_reports_no_stations(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    assert _stations(client, auth_headers, car["id"]) == []


def test_compute_station_stats_is_pure_on_empty_input() -> None:
    assert compute_station_stats([]) == []
