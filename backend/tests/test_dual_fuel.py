"""Per-refuel fuel kind (ГБО): independent full-to-full cycles per fuel.

The load-bearing rule these tests pin down: on an LPG car the petrol tank and
the gas tank are INDEPENDENT full-to-full cycles. A petrol fill in the middle
of a gas segment must not close, split or otherwise disturb that segment — it
only contributes the kilometres it was driven over, which is exactly why the
distance of a per-kind segment still spans every refuel in between.

The second rule is backward compatibility: a single-fuel car must produce the
same numbers it produced before fuel_kind existed. That is what the rest of
the suite asserts, so it is only spot-checked here.
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.services.fuel import (
    RefuelPoint,
    compute_fuel_stats,
    compute_stats_per_kind,
    effective_fuel_kind,
)

TODAY = dt.date.today()


# Engine-level: compute_fuel_stats(points, fuel_kind=...)


def _point(
    odometer: int,
    liters: float,
    is_full_tank: bool = True,
    fuel_kind: str | None = None,
    total_cost: float = 0.0,
    log_id: int | None = None,
) -> RefuelPoint:
    return RefuelPoint(
        date=TODAY,
        odometer=odometer,
        liters=liters,
        total_cost=total_cost,
        is_full_tank=is_full_tank,
        log_id=log_id,
        fuel_kind=fuel_kind,
    )


def test_intermediate_other_kind_refuel_does_not_break_a_segment() -> None:
    points = [
        _point(10000, 40, fuel_kind="lpg"),
        _point(10200, 30, fuel_kind="petrol"),
        _point(10400, 45, fuel_kind="lpg"),
    ]

    stats = compute_fuel_stats(points, fuel_kind="lpg")

    assert len(stats.history) == 1
    segment = stats.history[0]
    assert segment.distance_km == 400
    assert segment.liters == pytest.approx(45.0)
    assert segment.consumption_l_100km == pytest.approx(11.25)


def test_other_kind_liters_never_leak_into_a_segment() -> None:
    points = [
        _point(10000, 40, fuel_kind="lpg"),
        _point(10200, 30, is_full_tank=False, fuel_kind="petrol"),
        _point(10300, 10, is_full_tank=False, fuel_kind="lpg"),
        _point(10400, 35, fuel_kind="lpg"),
    ]

    stats = compute_fuel_stats(points, fuel_kind="lpg")

    assert len(stats.history) == 1
    # 10 L partial gas + 35 L closing gas = 45 L; the 30 L of petrol are not gas.
    assert stats.history[0].liters == pytest.approx(45.0)
    assert stats.history[0].distance_km == 400


def test_fuel_kind_none_measures_every_refuel_together() -> None:
    points = [
        _point(10000, 40, fuel_kind="lpg"),
        _point(10200, 30, fuel_kind="petrol"),
        _point(10400, 45, fuel_kind="lpg"),
    ]

    stats = compute_fuel_stats(points)

    assert [segment.distance_km for segment in stats.history] == [200, 200]


def test_unknown_kind_yields_empty_stats() -> None:
    points = [_point(10000, 40, fuel_kind="lpg"), _point(10400, 45, fuel_kind="lpg")]

    stats = compute_fuel_stats(points, fuel_kind="diesel")

    assert stats.history == []
    assert stats.avg_consumption_l_100km is None
    assert stats.last_consumption_l_100km is None
    assert stats.avg_cost_per_km is None
    assert stats.total_liters == 0.0
    assert stats.total_cost == 0.0


def test_totals_count_every_litre_of_the_kind_even_unmeasured_ones() -> None:
    """total_liters/total_cost are what you BOUGHT, not what was measured.

    The first fill anchors and can never be measured, but the money left the
    wallet all the same — a «total spent on gas» that hides it would be wrong.
    """
    points = [
        _point(10000, 40, fuel_kind="lpg", total_cost=800.0),
        _point(10400, 45, fuel_kind="lpg", total_cost=900.0),
        _point(10600, 30, fuel_kind="petrol", total_cost=1500.0),
    ]

    stats = compute_fuel_stats(points, fuel_kind="lpg")

    assert stats.total_liters == pytest.approx(85.0)
    assert stats.total_cost == pytest.approx(1700.0)
    # ...while the averages stay measured-only: 45 L / 400 km.
    assert stats.avg_consumption_l_100km == pytest.approx(11.25)
    assert stats.avg_cost_per_km == pytest.approx(2.25)


def test_compute_stats_per_kind_keys_off_the_kinds_actually_present() -> None:
    points = [
        _point(10000, 40, fuel_kind="lpg"),
        _point(10200, 30, fuel_kind="petrol"),
        _point(10400, 45, fuel_kind="lpg"),
        _point(10600, 25, fuel_kind="petrol"),
    ]

    per_kind = compute_stats_per_kind(points)

    assert set(per_kind) == {"lpg", "petrol"}
    # lpg: 45 L / 400 km; petrol: 25 L / 400 km (10200 -> 10600)
    assert per_kind["lpg"].avg_consumption_l_100km == pytest.approx(11.25)
    assert per_kind["petrol"].avg_consumption_l_100km == pytest.approx(6.25)


def test_compute_stats_per_kind_is_empty_without_refuels() -> None:
    assert compute_stats_per_kind([]) == {}


# effective_fuel_kind: the single place NULL resolves


class _FakeCar:
    def __init__(self, fuel_type: str) -> None:
        self.fuel_type = fuel_type


class _FakeRefuel:
    def __init__(self, fuel_kind: str | None) -> None:
        self.fuel_kind = fuel_kind


def test_effective_fuel_kind_falls_back_to_the_car() -> None:
    car = _FakeCar("diesel")
    assert effective_fuel_kind(_FakeRefuel(None), car) == "diesel"


def test_effective_fuel_kind_prefers_the_refuels_own_kind() -> None:
    car = _FakeCar("lpg")
    assert effective_fuel_kind(_FakeRefuel("petrol"), car) == "petrol"


# API level


def _refuel(
    client: TestClient,
    headers: dict,
    car_id: int,
    odometer: int,
    liters: float,
    total_cost: float,
    days_ago: int,
    fuel_kind: str | None = None,
    is_full_tank: bool = True,
    gas_station: str | None = None,
) -> dict:
    refuel: dict = {
        "liters": liters,
        "price_per_liter": round(total_cost / liters, 2),
        "is_full_tank": is_full_tank,
    }
    if fuel_kind is not None:
        refuel["fuel_kind"] = fuel_kind
    if gas_station is not None:
        refuel["gas_station"] = gas_station
    response = client.post(
        f"/api/cars/{car_id}/logs",
        json={
            "type": "refuel",
            "odometer": odometer,
            "date": (TODAY - dt.timedelta(days=days_ago)).isoformat(),
            "total_cost": total_cost,
            "refuel": refuel,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _analytics(client: TestClient, headers: dict, car_id: int) -> dict:
    response = client.get(f"/api/cars/{car_id}/analytics", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _seed_lpg_car(client: TestClient, headers: dict, make_car) -> dict:
    car = make_car(fuel_type="lpg", current_odometer=10800)
    _refuel(client, headers, car["id"], 10000, 40, 800.0, 50, fuel_kind="lpg")
    _refuel(client, headers, car["id"], 10200, 30, 1500.0, 40, fuel_kind="petrol")
    _refuel(client, headers, car["id"], 10400, 45, 900.0, 30, fuel_kind="lpg")
    _refuel(client, headers, car["id"], 10600, 25, 1250.0, 20, fuel_kind="petrol")
    _refuel(client, headers, car["id"], 10800, 40, 800.0, 10, fuel_kind="lpg")
    return car


def test_lpg_car_reports_two_independent_averages(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = _seed_lpg_car(client, auth_headers, make_car)

    by_kind = _analytics(client, auth_headers, car["id"])["fuel"]["by_kind"]

    assert set(by_kind) == {"lpg", "petrol"}

    # Gas: 45 L / 400 km = 11.25 and 40 L / 400 km = 10.0 -> 85 L / 800 km.
    gas = by_kind["lpg"]
    # 85 L / 800 km = 10.625, reported at the engine's own 2-dp rounding.
    assert gas["avg_consumption_l_100km"] == pytest.approx(10.625, abs=0.01)
    assert gas["last_consumption_l_100km"] == pytest.approx(10.0)
    assert gas["avg_cost_per_km"] == pytest.approx(2.125, abs=0.001)
    assert gas["total_liters"] == pytest.approx(125.0)
    assert gas["total_cost"] == pytest.approx(2500.0)

    # Petrol: one segment 10200 -> 10600, 25 L / 400 km = 6.25.
    petrol = by_kind["petrol"]
    assert petrol["avg_consumption_l_100km"] == pytest.approx(6.25)
    assert petrol["last_consumption_l_100km"] == pytest.approx(6.25)
    assert petrol["avg_cost_per_km"] == pytest.approx(3.125, abs=0.001)
    assert petrol["total_liters"] == pytest.approx(55.0)
    assert petrol["total_cost"] == pytest.approx(2750.0)


def test_each_kind_carries_its_own_segment_history(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = _seed_lpg_car(client, auth_headers, make_car)

    by_kind = _analytics(client, auth_headers, car["id"])["fuel"]["by_kind"]

    gas_history = by_kind["lpg"]["history"]
    assert [segment["consumption_l_100km"] for segment in gas_history] == [11.25, 10.0]
    # Both gas segments span an intervening petrol fill, and neither is split.
    assert [segment["distance_km"] for segment in gas_history] == [400, 400]

    assert [segment["consumption_l_100km"] for segment in by_kind["petrol"]["history"]] == [
        6.25
    ]


def test_single_fuel_history_is_the_same_list_in_both_places(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(fuel_type="petrol", current_odometer=10800)
    _refuel(client, auth_headers, car["id"], 10000, 40, 800.0, 30)
    _refuel(client, auth_headers, car["id"], 10400, 20, 400.0, 20)

    fuel = _analytics(client, auth_headers, car["id"])["fuel"]

    assert fuel["by_kind"]["petrol"]["history"] == fuel["history"]


def test_lpg_top_level_fuel_block_is_the_cars_own_kind(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """`fuel.*` is the aggregate for the car's own fuel type, not a mix.

    A blended average over two tanks is a number with no physical meaning; the
    legacy block reports gas for a gas car and matches by_kind['lpg'] exactly.
    """
    car = _seed_lpg_car(client, auth_headers, make_car)

    fuel = _analytics(client, auth_headers, car["id"])["fuel"]

    assert fuel["avg_consumption_l_100km"] == pytest.approx(10.625, abs=0.01)
    assert fuel["avg_consumption_l_100km"] == fuel["by_kind"]["lpg"]["avg_consumption_l_100km"]
    # Two gas segments, each spanning an intervening petrol fill.
    assert [segment["distance_km"] for segment in fuel["history"]] == [400, 400]


def test_single_fuel_car_is_unchanged_and_has_one_kind(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(fuel_type="petrol", current_odometer=10800)
    _refuel(client, auth_headers, car["id"], 10000, 40, 800.0, 30)
    _refuel(client, auth_headers, car["id"], 10400, 20, 400.0, 20)
    _refuel(client, auth_headers, car["id"], 10800, 25, 500.0, 10)

    fuel = _analytics(client, auth_headers, car["id"])["fuel"]

    assert set(fuel["by_kind"]) == {"petrol"}
    petrol = fuel["by_kind"]["petrol"]
    assert petrol["avg_consumption_l_100km"] == fuel["avg_consumption_l_100km"]
    assert petrol["last_consumption_l_100km"] == fuel["last_consumption_l_100km"]
    assert petrol["avg_cost_per_km"] == fuel["avg_cost_per_km"]
    # 20 L / 400 km = 5.0 and 25 L / 400 km = 6.25
    assert [segment["consumption_l_100km"] for segment in fuel["history"]] == [5.0, 6.25]


def test_car_without_refuels_reports_no_kinds(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    assert _analytics(client, auth_headers, car["id"])["fuel"]["by_kind"] == {}


def test_null_fuel_kind_inherits_the_car_type(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """A legacy row (NULL) and an explicit row of the car's own type are one kind."""
    car = make_car(fuel_type="diesel", current_odometer=10800)
    _refuel(client, auth_headers, car["id"], 10000, 40, 800.0, 30)  # NULL
    _refuel(client, auth_headers, car["id"], 10400, 20, 400.0, 20, fuel_kind="diesel")
    _refuel(client, auth_headers, car["id"], 10800, 25, 500.0, 10)  # NULL

    fuel = _analytics(client, auth_headers, car["id"])["fuel"]

    assert set(fuel["by_kind"]) == {"diesel"}
    # One group -> the segments are unbroken, exactly as if fuel_kind never existed.
    assert [segment["distance_km"] for segment in fuel["history"]] == [400, 400]


def test_fuel_kind_round_trips_through_create_and_patch(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(fuel_type="lpg", current_odometer=10000)
    log = _refuel(client, auth_headers, car["id"], 10000, 40, 800.0, 5, fuel_kind="petrol")
    assert log["refuel"]["fuel_kind"] == "petrol"

    patched = client.patch(
        f"/api/logs/{log['id']}",
        json={"refuel": {"fuel_kind": "lpg"}},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["refuel"]["fuel_kind"] == "lpg"


def test_fuel_kind_can_be_cleared_back_to_the_car_default(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(fuel_type="lpg", current_odometer=10000)
    log = _refuel(client, auth_headers, car["id"], 10000, 40, 800.0, 5, fuel_kind="petrol")

    patched = client.patch(
        f"/api/logs/{log['id']}",
        json={"refuel": {"fuel_kind": None}},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["refuel"]["fuel_kind"] is None


def test_omitted_fuel_kind_stays_null(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """NULL is «as the car» — creating without a kind must not guess one."""
    car = make_car(fuel_type="petrol", current_odometer=10000)
    log = _refuel(client, auth_headers, car["id"], 10000, 40, 800.0, 5)
    assert log["refuel"]["fuel_kind"] is None


def test_unknown_fuel_kind_is_rejected(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(fuel_type="lpg", current_odometer=10000)
    response = client.post(
        f"/api/cars/{car['id']}/logs",
        json={
            "type": "refuel",
            "odometer": 10000,
            "date": TODAY.isoformat(),
            "total_cost": 800,
            "refuel": {
                "liters": 40,
                "price_per_liter": 20,
                "is_full_tank": True,
                "fuel_kind": "coal",
            },
        },
        headers=auth_headers,
    )
    assert response.status_code == 422, response.text


def test_logbook_consumption_is_measured_within_its_own_kind(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """The per-row number in the journal follows the same independent cycles.

    Without this the gas fill at 10400 would read as «45 L over the 200 km
    since the petrol fill», which is not a thing that happened.
    """
    car = _seed_lpg_car(client, auth_headers, make_car)

    response = client.get(f"/api/cars/{car['id']}/logs", headers=auth_headers)
    assert response.status_code == 200, response.text
    by_odometer = {
        item["odometer"]: item["refuel"]["consumption_l_100km"]
        for item in response.json()["items"]
    }

    assert by_odometer[10000] is None  # anchors its kind, closes nothing
    assert by_odometer[10200] is None  # anchors petrol
    assert by_odometer[10400] == pytest.approx(11.25)  # gas, 45 L / 400 km
    assert by_odometer[10600] == pytest.approx(6.25)  # petrol, 25 L / 400 km
    assert by_odometer[10800] == pytest.approx(10.0)  # gas, 40 L / 400 km


def test_station_consumption_follows_its_own_kind(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(fuel_type="lpg", current_odometer=10400)
    _refuel(
        client, auth_headers, car["id"], 10000, 40, 800.0, 30,
        fuel_kind="lpg", gas_station="OKKO",
    )
    _refuel(
        client, auth_headers, car["id"], 10200, 30, 1500.0, 20,
        fuel_kind="petrol", gas_station="WOG",
    )
    _refuel(
        client, auth_headers, car["id"], 10400, 45, 900.0, 10,
        fuel_kind="lpg", gas_station="UPG",
    )

    stations = {
        station["name"]: station
        for station in _analytics(client, auth_headers, car["id"])["stations"]
    }

    # OKKO anchored the gas segment closed at 10400: 45 L over 400 km.
    assert stations["OKKO"]["avg_consumption_l_100km"] == pytest.approx(11.25)
    # WOG only anchored a petrol segment that never closed.
    assert stations["WOG"]["avg_consumption_l_100km"] is None
    assert stations["UPG"]["avg_consumption_l_100km"] is None


def test_car_reports_the_fuel_kinds_it_actually_used(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = _seed_lpg_car(client, auth_headers, make_car)

    response = client.get("/api/cars", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = next(item for item in response.json() if item["id"] == car["id"])

    assert sorted(body["fuel_kinds_used"]) == ["lpg", "petrol"]


def test_single_fuel_car_reports_one_kind_used(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(fuel_type="petrol", current_odometer=10000)
    _refuel(client, auth_headers, car["id"], 10000, 40, 800.0, 5)

    response = client.get("/api/cars", headers=auth_headers)
    body = next(item for item in response.json() if item["id"] == car["id"])

    # The NULL row resolves to the car's own type — one kind, so no selector.
    assert body["fuel_kinds_used"] == ["petrol"]


def test_car_without_refuels_reports_no_kinds_used(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(fuel_type="petrol")
    response = client.get("/api/cars", headers=auth_headers)
    body = next(item for item in response.json() if item["id"] == car["id"])
    assert body["fuel_kinds_used"] == []
