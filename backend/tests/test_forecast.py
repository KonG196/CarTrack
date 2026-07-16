"""Forecast unit tests (pinned dates) and analytics endpoint shape tests."""

import datetime as dt
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import event

from app.models import LogEntry, MaintenanceDetails, RepairDetails
from app.services.forecast import (
    compute_avg_monthly_spend,
    compute_monthly_km_rate,
    compute_projected_month_total,
    estimate_interval_cost,
)

PINNED_TODAY = dt.date(2026, 7, 15)


def make_log(
    type_: str = "expense",
    odometer: int = 10000,
    date: dt.date = PINNED_TODAY,
    total_cost: float = 0,
    notes: str | None = None,
    items: list[str] | None = None,
    category: str | None = None,
    part_name: str | None = None,
) -> LogEntry:
    log = LogEntry(
        type=type_,
        odometer=odometer,
        date=date,
        total_cost=Decimal(str(total_cost)),
        notes=notes,
    )
    if items is not None:
        log.maintenance = MaintenanceDetails(items=items)
    if category is not None:
        log.repair = RepairDetails(category=category, part_name=part_name)
    return log


# compute_monthly_km_rate


def test_monthly_km_rate_from_known_span() -> None:
    logs = [
        make_log(odometer=10000, date=dt.date(2026, 1, 1)),
        make_log(odometer=13000, date=dt.date(2026, 3, 2)),
    ]
    # 3000 km over 60 days -> 1500 km per 30 days.
    assert compute_monthly_km_rate(logs) == 1500.0


def test_monthly_km_rate_requires_two_logs() -> None:
    assert compute_monthly_km_rate([]) is None
    assert compute_monthly_km_rate([make_log(odometer=10000)]) is None


def test_monthly_km_rate_requires_week_span() -> None:
    logs = [
        make_log(odometer=10000, date=dt.date(2026, 7, 1)),
        make_log(odometer=10500, date=dt.date(2026, 7, 4)),
    ]
    assert compute_monthly_km_rate(logs) is None


# compute_avg_monthly_spend


def test_avg_monthly_spend_over_six_complete_months() -> None:
    logs = [
        # Seventh most recent month with data: beyond the 6-month window.
        make_log(date=dt.date(2025, 12, 10), total_cost=9999),
        make_log(date=dt.date(2026, 1, 10), total_cost=100),
        make_log(date=dt.date(2026, 2, 10), total_cost=200),
        make_log(date=dt.date(2026, 3, 10), total_cost=300),
        make_log(date=dt.date(2026, 4, 10), total_cost=250),
        make_log(date=dt.date(2026, 4, 20), total_cost=150),
        make_log(date=dt.date(2026, 5, 10), total_cost=500),
        make_log(date=dt.date(2026, 6, 10), total_cost=600),
        # Current partial month: ignored.
        make_log(date=dt.date(2026, 7, 5), total_cost=777),
    ]
    # Jan..Jun totals: 100, 200, 300, 400, 500, 600 -> mean 350.
    assert compute_avg_monthly_spend(logs, today=PINNED_TODAY) == 350.0


def test_avg_monthly_spend_none_without_complete_month_data() -> None:
    assert compute_avg_monthly_spend([], today=PINNED_TODAY) is None
    only_current = [make_log(date=dt.date(2026, 7, 5), total_cost=100)]
    assert compute_avg_monthly_spend(only_current, today=PINNED_TODAY) is None


# compute_projected_month_total


def test_projected_month_total_mid_month() -> None:
    logs = [
        # Outside the 90-day window: ignored entirely.
        make_log(date=dt.date(2026, 1, 15), total_cost=5000),
        # In the window but not this month.
        make_log(date=dt.date(2026, 5, 1), total_cost=900),
        # This month, up to today.
        make_log(date=dt.date(2026, 7, 10), total_cost=900),
    ]
    # Window spend 1800 over 90 days -> 20/day; July 15: spent 900,
    # 16 days remain of 31 -> 900 + 20 * 16 = 1220.
    assert compute_projected_month_total(logs, today=PINNED_TODAY) == 1220.0


def test_projected_month_total_none_without_recent_data() -> None:
    assert compute_projected_month_total([], today=PINNED_TODAY) is None
    old_logs = [make_log(date=dt.date(2026, 1, 15), total_cost=5000)]
    assert compute_projected_month_total(old_logs, today=PINNED_TODAY) is None


def test_projected_month_total_on_first_day_of_month() -> None:
    logs = [make_log(date=dt.date(2026, 7, 1), total_cost=900)]
    # 900 spent today; daily rate 10/day over 30 remaining July days -> 1200.
    assert compute_projected_month_total(logs, today=dt.date(2026, 7, 1)) == 1200.0


def test_projected_month_total_on_last_day_of_month() -> None:
    logs = [make_log(date=dt.date(2026, 7, 10), total_cost=900)]
    # Zero days remain: projection equals the month's actual spend.
    assert compute_projected_month_total(logs, today=dt.date(2026, 7, 31)) == 900.0


def test_projected_month_total_single_log_in_window() -> None:
    # One log 25 days ago, previous month: rate 5/day, nothing spent in July.
    logs = [make_log(date=dt.date(2026, 6, 20), total_cost=450)]
    assert compute_projected_month_total(logs, today=PINNED_TODAY) == 80.0


def test_avg_monthly_spend_december_january_boundary() -> None:
    # On Jan 1 the whole of December is a complete month and must count.
    logs = [make_log(date=dt.date(2025, 12, 31), total_cost=600)]
    assert compute_avg_monthly_spend(logs, today=dt.date(2026, 1, 1)) == 600.0


def test_avg_monthly_spend_ignores_future_months() -> None:
    logs = [
        make_log(date=dt.date(2026, 6, 10), total_cost=300),
        make_log(date=dt.date(2026, 8, 10), total_cost=9000),
        make_log(date=dt.date(2027, 1, 10), total_cost=9000),
    ]
    assert compute_avg_monthly_spend(logs, today=PINNED_TODAY) == 300.0


# estimate_interval_cost


def test_estimate_interval_cost_median_of_matches() -> None:
    logs = [
        make_log(
            type_="maintenance",
            total_cost=1500,
            items=["Олива двигуна", "Масляний фільтр"],
        ),
        make_log(
            type_="maintenance",
            total_cost=1800,
            items=["Олива двигуна", "Масляний фільтр"],
        ),
        make_log(
            type_="maintenance",
            total_cost=2100,
            items=["Олива двигуна"],
        ),
        # No keyword overlap with the interval title: not counted.
        make_log(type_="repair", total_cost=9000, category="Підвіска", part_name="Амортизатор"),
        # Refuels are never counted even with matching notes.
        make_log(type_="refuel", total_cost=2000, notes="після заміни оливи двигуна"),
    ]
    estimate = estimate_interval_cost("Заміна оливи двигуна", logs)
    assert estimate.amount == 1800.0
    assert estimate.source == "history"


def test_unrelated_history_is_not_borrowed_for_a_different_service() -> None:
    """An oil bill says nothing about brake pads. Without a matching record the
    answer falls back to the market — and says so, so the number is never
    mistaken for this car's own."""
    logs = [
        make_log(
            type_="maintenance",
            total_cost=1500,
            items=["Олива двигуна", "Масляний фільтр"],
        ),
    ]
    pads = estimate_interval_cost("Гальмівні колодки", logs)
    assert pads.source == "baseline"
    assert pads.amount != 1500

    first_ever = estimate_interval_cost("Заміна оливи двигуна", [])
    assert first_ever.source == "baseline"


def test_estimate_interval_cost_stop_words_prevent_generic_match() -> None:
    # Both texts contain "заміна", but that alone must never link an oil
    # interval to a brake-pads log.
    logs = [
        make_log(
            type_="repair",
            total_cost=4000,
            category="Гальма",
            part_name="Колодки",
            notes="заміна передніх гальмівних колодок",
        ),
    ]
    estimate = estimate_interval_cost("Заміна оливи", logs)
    assert estimate.source == "baseline"
    assert estimate.amount != 4000  # never the brake-pads bill


def test_estimate_interval_cost_title_of_only_stop_words_returns_none() -> None:
    logs = [make_log(type_="maintenance", total_cost=1000, items=["Олива двигуна"])]
    assert estimate_interval_cost("Заміна", logs) is None


def test_estimate_interval_cost_median_of_even_matches() -> None:
    logs = [
        make_log(type_="maintenance", total_cost=1000, items=["Олива двигуна"]),
        make_log(type_="maintenance", total_cost=2000, items=["Олива двигуна"]),
    ]
    assert estimate_interval_cost("Олива двигуна", logs).amount == 1500.0


def test_estimate_interval_cost_normalizes_case_and_punctuation() -> None:
    logs = [make_log(type_="maintenance", total_cost=1200, items=["олива, двигуна!"])]
    assert estimate_interval_cost("ОЛИВА ДВИГУНА", logs).amount == 1200.0


# /analytics endpoint: forecast key


def _post_interval(client: TestClient, headers: dict, car_id: int, payload: dict) -> dict:
    response = client.post(f"/api/cars/{car_id}/intervals", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_analytics_forecast_shape_for_empty_car(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    response = client.get(f"/api/cars/{car['id']}/analytics", headers=auth_headers)
    assert response.status_code == 200
    forecast = response.json()["forecast"]

    assert set(forecast.keys()) == {
        "monthly_km_rate",
        "avg_monthly_spend",
        "projected_month_total",
        "upcoming",
    }
    assert forecast["monthly_km_rate"] is None
    assert forecast["avg_monthly_spend"] is None
    assert forecast["projected_month_total"] is None
    assert forecast["upcoming"] == []


def test_forecast_upcoming_includes_due_and_soon_sorted(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    # No logs: avg_daily_km falls back to 40 km/day for predictions.
    car = make_car(current_odometer=10000)
    car_id = car["id"]

    overdue = _post_interval(
        client,
        auth_headers,
        car_id,
        {"title": "Прострочене ТО", "interval_km": 5000, "last_odometer": 2000},
    )
    due_soon = _post_interval(
        client,
        auth_headers,
        car_id,
        {"title": "Скоро ТО", "interval_km": 5000, "last_odometer": 5500},
    )
    within_horizon = _post_interval(
        client,
        auth_headers,
        car_id,
        # km_left 3000 -> ok status, but predicted in ~75 days (< 90).
        {"title": "У межах горизонту", "interval_km": 5000, "last_odometer": 8000},
    )
    _post_interval(
        client,
        auth_headers,
        car_id,
        # km_left 100000 -> predicted in ~2500 days: excluded.
        {"title": "Далеке ТО", "interval_km": 100000, "last_odometer": 10000},
    )

    response = client.get(f"/api/cars/{car_id}/analytics", headers=auth_headers)
    assert response.status_code == 200
    upcoming = response.json()["forecast"]["upcoming"]

    assert [item["interval_id"] for item in upcoming] == [
        overdue["id"],
        due_soon["id"],
        within_horizon["id"],
    ]
    for item in upcoming:
        assert set(item.keys()) == {
            "interval_id",
            "title",
            "predicted_due_date",
            "km_left",
            "days_left",
            "estimated_cost",
            "estimated_cost_source",
        }

    assert upcoming[0]["km_left"] == -3000
    assert upcoming[1]["km_left"] == 500
    assert upcoming[2]["km_left"] == 3000
    # No service logs exist, so no interval has a cost estimate.
    assert all(item["estimated_cost"] is None for item in upcoming)


def test_forecast_estimated_cost_from_matching_logs(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    car_id = car["id"]

    response = client.post(
        f"/api/cars/{car_id}/logs",
        json={
            "type": "maintenance",
            "odometer": 9500,
            "date": dt.date.today().isoformat(),
            "total_cost": 1750,
            "maintenance": {
                "parts_cost": 1500,
                "labor_cost": 250,
                "items": ["Олива двигуна", "Масляний фільтр"],
            },
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text

    interval = _post_interval(
        client,
        auth_headers,
        car_id,
        {"title": "Заміна оливи двигуна", "interval_km": 10000, "last_odometer": 500},
    )

    response = client.get(f"/api/cars/{car_id}/analytics", headers=auth_headers)
    assert response.status_code == 200
    upcoming = response.json()["forecast"]["upcoming"]
    match = next(item for item in upcoming if item["interval_id"] == interval["id"])
    assert match["estimated_cost"] == 1750.0


def test_forecast_estimated_cost_scoped_to_one_car(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """A matching service log on another car must not feed the estimate."""
    car_a = make_car(current_odometer=10000)
    car_b = make_car(current_odometer=10000)

    response = client.post(
        f"/api/cars/{car_b['id']}/logs",
        json={
            "type": "maintenance",
            "odometer": 9500,
            "date": dt.date.today().isoformat(),
            "total_cost": 1750,
            "maintenance": {
                "parts_cost": 1500,
                "labor_cost": 250,
                "items": ["Олива двигуна", "Масляний фільтр"],
            },
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text

    interval = _post_interval(
        client,
        auth_headers,
        car_a["id"],
        {"title": "Заміна оливи двигуна", "interval_km": 10000, "last_odometer": 500},
    )

    response = client.get(f"/api/cars/{car_a['id']}/analytics", headers=auth_headers)
    assert response.status_code == 200
    upcoming = response.json()["forecast"]["upcoming"]
    match = next(item for item in upcoming if item["interval_id"] == interval["id"])
    # Car A has no history of its own, so it gets the market ballpark — and
    # never car B's 1750, which is the whole point of the test.
    assert match["estimated_cost"] != 1750
    assert match["estimated_cost_source"] == "baseline"


# /analytics endpoint: query efficiency (no per-log lazy loading)


def _count_selects_during_get(client: TestClient, db_engine, url: str, headers: dict) -> int:
    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(db_engine, "before_cursor_execute", before_cursor_execute)
    try:
        response = client.get(url, headers=headers)
    finally:
        event.remove(db_engine, "before_cursor_execute", before_cursor_execute)
    assert response.status_code == 200, response.text
    return len(statements)


def test_analytics_query_count_does_not_scale_with_logs(
    client: TestClient, auth_headers: dict, make_car, db_engine
) -> None:
    """Log detail rows must be eager-loaded, not lazy-loaded per log (N+1)."""
    counts: list[int] = []
    for n_logs in (2, 12):
        car = make_car(current_odometer=20000)
        for i in range(n_logs):
            payload = {
                "type": "maintenance" if i % 2 else "refuel",
                "odometer": 10000 + i * 100,
                "date": (dt.date.today() - dt.timedelta(days=n_logs - i)).isoformat(),
                "total_cost": 500,
            }
            if payload["type"] == "maintenance":
                payload["maintenance"] = {
                    "parts_cost": 400,
                    "labor_cost": 100,
                    "items": ["Олива двигуна"],
                }
            else:
                payload["refuel"] = {"liters": 40, "price_per_liter": 55, "is_full_tank": True}
            response = client.post(
                f"/api/cars/{car['id']}/logs", json=payload, headers=auth_headers
            )
            assert response.status_code == 201, response.text
        response = client.post(
            f"/api/cars/{car['id']}/intervals",
            json={"title": "Заміна оливи двигуна", "interval_km": 10000, "last_odometer": 10000},
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text
        counts.append(
            _count_selects_during_get(
                client, db_engine, f"/api/cars/{car['id']}/analytics", auth_headers
            )
        )

    assert counts[0] == counts[1], f"query count grew with log count: {counts}"
