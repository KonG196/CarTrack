"""Service interval status engine tests: ok / due_soon / overdue and CRUD."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.models import LogEntry
from app.services.intervals import DEFAULT_AVG_DAILY_KM, compute_avg_daily_km

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


def _add_maintenance(client, headers, car_id, *, odometer, items, date=None):
    resp = client.post(
        f"/api/cars/{car_id}/logs",
        json={
            "type": "maintenance",
            "odometer": odometer,
            "date": (date or TODAY).isoformat(),
            "total_cost": 100,
            "maintenance": {"parts_cost": 60, "labor_cost": 40, "items": items},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _get_interval(client, headers, car_id, interval_id):
    resp = client.get(f"/api/cars/{car_id}/intervals", headers=headers)
    assert resp.status_code == 200
    return next(i for i in resp.json() if i["id"] == interval_id)


def test_logging_a_service_advances_the_matching_interval(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """Юра's case: an oil change logged in the journal moves the oil interval,
    without a second «Done» tap."""
    car = make_car(current_odometer=45000)
    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {"title": "Oil change", "interval_km": 10000, "last_odometer": 40000},
    )
    assert interval["km_left"] == 5000  # 40000+10000-45000

    _add_maintenance(client, auth_headers, car["id"], odometer=45000, items=["Oil change"])

    updated = _get_interval(client, auth_headers, car["id"], interval["id"])
    assert updated["last_odometer"] == 45000
    assert updated["due_odometer"] == 55000
    assert updated["km_left"] == 10000  # freshly serviced -> full interval ahead


def test_logging_a_service_never_moves_an_interval_backwards(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=60000)
    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {"title": "Oil change", "interval_km": 10000, "last_odometer": 55000},
    )
    # Backfilling an older oil change (at 30000) must not un-service the car.
    _add_maintenance(
        client,
        auth_headers,
        car["id"],
        odometer=30000,
        items=["Oil change"],
        date=TODAY - dt.timedelta(days=400),
    )
    updated = _get_interval(client, auth_headers, car["id"], interval["id"])
    assert updated["last_odometer"] == 55000  # unchanged


def test_unrelated_service_does_not_touch_the_interval(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=45000)
    interval = _create_interval(
        client,
        auth_headers,
        car["id"],
        {"title": "Oil change", "interval_km": 10000, "last_odometer": 40000},
    )
    _add_maintenance(client, auth_headers, car["id"], odometer=45000, items=["Air filter"])
    updated = _get_interval(client, auth_headers, car["id"], interval["id"])
    assert updated["last_odometer"] == 40000  # oil interval untouched


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


# avg_daily_km: a rolling window, not the car's whole life


def _logs(*pairs: tuple[dt.date, int]) -> list[LogEntry]:
    """Throwaway LogEntry objects; the pace engine only reads date+odometer."""
    return [LogEntry(car_id=1, type="expense", date=d, odometer=o) for d, o in pairs]


def test_avg_daily_km_uses_the_last_90_days() -> None:
    logs = _logs(
        (TODAY - dt.timedelta(days=400), 0),  # ancient history: 100 km/day
        (TODAY - dt.timedelta(days=200), 20000),
        (TODAY - dt.timedelta(days=60), 30000),  # the window starts here
        (TODAY, 31200),  # 1200 km over 60 days -> 20 km/day
    )
    assert compute_avg_daily_km(logs, today=TODAY) == 20.0


def test_avg_daily_km_window_widens_to_180_then_365_when_data_is_thin() -> None:
    # Only one log inside 90 days -> widen to 180, which has two.
    logs = _logs(
        (TODAY - dt.timedelta(days=170), 10000),
        (TODAY - dt.timedelta(days=70), 12000),  # 2000 km over 100 days -> 20/day
    )
    assert compute_avg_daily_km(logs, today=TODAY) == 20.0

    # Nothing inside 180 either -> widen to 365.
    logs = _logs(
        (TODAY - dt.timedelta(days=360), 10000),
        (TODAY - dt.timedelta(days=260), 13000),  # 3000 km over 100 days -> 30/day
    )
    assert compute_avg_daily_km(logs, today=TODAY) == 30.0


def test_avg_daily_km_window_widens_when_the_span_is_under_a_week() -> None:
    logs = _logs(
        (TODAY - dt.timedelta(days=300), 0),
        (TODAY - dt.timedelta(days=3), 24000),
        (TODAY, 24300),  # a 300 km weekend -> 100 km/day, too short to trust
    )
    # 90 and 180 both span only 3 days, so the 365 window answers:
    # 24300 km over 300 days -> 81 km/day, not the 100 of the weekend.
    assert compute_avg_daily_km(logs, today=TODAY) == 81.0


def test_avg_daily_km_falls_back_to_lifetime_then_to_the_default() -> None:
    # Everything older than a year -> lifetime average.
    logs = _logs(
        (TODAY - dt.timedelta(days=1000), 0),
        (TODAY - dt.timedelta(days=500), 25000),  # 25000 km / 500 days -> 50/day
    )
    assert compute_avg_daily_km(logs, today=TODAY) == 50.0

    # A single log carries no pace at all.
    assert compute_avg_daily_km(_logs((TODAY, 1000)), today=TODAY) == DEFAULT_AVG_DAILY_KM
    assert compute_avg_daily_km([], today=TODAY) == DEFAULT_AVG_DAILY_KM


def test_avg_daily_km_spans_the_window_extremes_not_its_first_and_last_row() -> None:
    """Min/max keep a mistyped reading from making the delta negative.

    First-and-last would read -26880 km here, give up, and hand back the 40
    km/day default for a car with a perfectly usable 60-day history.
    """
    logs = _logs(
        (TODAY - dt.timedelta(days=60), 30000),
        (TODAY - dt.timedelta(days=30), 31200),
        (TODAY, 3120),  # a typo: a digit dropped
    )
    assert compute_avg_daily_km(logs, today=TODAY) == pytest.approx(28080 / 60)


# The owner's real Golf history: 19 logs, Germany 2016-2022, Ukraine 2022-2026.
GOLF_LOGS: tuple[tuple[str, int], ...] = (
    ("2016-07-15", 0),
    ("2017-12-20", 34104),
    ("2018-03-07", 60857),
    ("2019-08-23", 93636),
    ("2020-02-26", 105478),
    ("2020-07-02", 122507),
    ("2021-06-30", 146617),
    ("2022-10-19", 189000),
    ("2022-12-03", 190011),
    ("2022-12-23", 190563),
    ("2023-03-17", 193437),
    ("2023-10-06", 202373),
    ("2023-11-17", 204017),
    ("2024-08-13", 214600),
    ("2025-06-15", 236000),
    ("2025-07-18", 224900),
    ("2026-05-08", 235700),
    ("2026-06-15", 238000),
    ("2026-07-06", 238150),
)


def test_golf_pace_comes_from_the_ukrainian_period_not_the_german_one() -> None:
    """The bug this replaces: 66 km/day averaged over the car's whole life.

    The German years ran the car far harder than the Ukrainian ones, and the
    ТО forecast is built on this number — so the window must describe how the
    car is driven *now*.
    """
    today = dt.date(2026, 7, 15)
    logs = _logs(*((dt.date.fromisoformat(d), o) for d, o in GOLF_LOGS))

    windowed = compute_avg_daily_km(logs, today=today)

    # The 90-day window holds 2026-05-08 (235700) .. 2026-07-06 (238150):
    # 2450 km over 59 days.
    assert windowed == pytest.approx(2450 / 59, abs=0.05)
    assert 35.0 < windowed < 50.0

    # The old lifetime average, for contrast: ~65 km/day over ~10 years.
    lifetime = 238150 / (dt.date(2026, 7, 6) - dt.date(2016, 7, 15)).days
    assert lifetime > 60.0
    assert windowed < lifetime * 0.75
