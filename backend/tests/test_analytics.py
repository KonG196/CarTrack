"""Analytics endpoint tests: response shape, totals and monthly buckets."""

import datetime as dt

from fastapi.testclient import TestClient

TODAY = dt.date.today()


def months_ago(day: dt.date, n: int) -> dt.date:
    year, month = day.year, day.month - n
    while month <= 0:
        month += 12
        year -= 1
    return dt.date(year, month, 1)


def month_key(day: dt.date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _post_log(client: TestClient, headers: dict, car_id: int, payload: dict) -> None:
    response = client.post(f"/api/cars/{car_id}/logs", json=payload, headers=headers)
    assert response.status_code == 201, response.text


def test_analytics_shape_for_empty_car(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    response = client.get(f"/api/cars/{car['id']}/analytics", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()

    assert set(body.keys()) == {
        "totals",
        "monthly",
        "expense_by_category",
        "stations",
        "fuel",
        "price_history",
        "forecast",
        "range_km",
        "budget",
    }
    assert body["stations"] == []
    # An empty car has neither a tank volume nor a budget set: both cards are
    # absent rather than zeroed. See test_range.py / test_budget.py.
    assert body["range_km"] is None
    assert body["budget"] is None
    assert body["totals"]["all_time"] == 0.0
    assert body["totals"]["this_month"] == 0.0
    assert body["totals"]["by_type"] == {
        "refuel": 0.0,
        "maintenance": 0.0,
        "repair": 0.0,
        "expense": 0.0,
    }

    assert len(body["monthly"]) == 12
    assert body["monthly"][-1]["month"] == month_key(TODAY)
    assert body["monthly"][0]["month"] == month_key(months_ago(TODAY, 11))
    assert all(bucket["total"] == 0.0 for bucket in body["monthly"])

    assert body["fuel"]["avg_consumption_l_100km"] is None
    assert body["fuel"]["last_consumption_l_100km"] is None
    assert body["fuel"]["avg_cost_per_km"] is None
    assert body["fuel"]["history"] == []


def test_analytics_totals_and_monthly_buckets(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    car_id = car["id"]

    # This month: one refuel (100) + one maintenance (200).
    _post_log(
        client,
        auth_headers,
        car_id,
        {
            "type": "refuel",
            "odometer": 10100,
            "date": TODAY.isoformat(),
            "total_cost": 100,
            "refuel": {"liters": 50, "price_per_liter": 2.0, "is_full_tank": True},
        },
    )
    _post_log(
        client,
        auth_headers,
        car_id,
        {
            "type": "maintenance",
            "odometer": 10200,
            "date": TODAY.isoformat(),
            "total_cost": 200,
            "maintenance": {"parts_cost": 150, "labor_cost": 50, "items": ["oil", "filter"]},
        },
    )
    # Three months ago: an expense (50) - inside the 12-month window.
    expense_date = months_ago(TODAY, 3)
    _post_log(
        client,
        auth_headers,
        car_id,
        {
            "type": "expense",
            "odometer": 9000,
            "date": expense_date.isoformat(),
            "total_cost": 50,
            "notes": "parking",
        },
    )
    # Fourteen months ago: a repair (75) - outside the monthly window,
    # but still part of all-time totals.
    _post_log(
        client,
        auth_headers,
        car_id,
        {
            "type": "repair",
            "odometer": 5000,
            "date": months_ago(TODAY, 14).isoformat(),
            "total_cost": 75,
            "repair": {"category": "suspension"},
        },
    )

    response = client.get(f"/api/cars/{car_id}/analytics", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()

    totals = body["totals"]
    assert totals["all_time"] == 425.0
    assert totals["this_month"] == 300.0
    assert totals["by_type"] == {
        "refuel": 100.0,
        "maintenance": 200.0,
        "repair": 75.0,
        "expense": 50.0,
    }

    monthly = body["monthly"]
    assert len(monthly) == 12
    assert [bucket["month"] for bucket in monthly] == [
        month_key(months_ago(TODAY, 11 - i)) for i in range(12)
    ]

    current = monthly[-1]
    assert current["refuel"] == 100.0
    assert current["maintenance"] == 200.0
    assert current["total"] == 300.0

    expense_bucket = next(b for b in monthly if b["month"] == month_key(expense_date))
    assert expense_bucket["expense"] == 50.0
    assert expense_bucket["total"] == 50.0

    # The 14-month-old repair is not in any monthly bucket.
    assert sum(bucket["repair"] for bucket in monthly) == 0.0
    # Bucket sums line up with their totals.
    for bucket in monthly:
        parts = bucket["refuel"] + bucket["maintenance"] + bucket["repair"] + bucket["expense"]
        assert abs(bucket["total"] - parts) < 0.001


def test_analytics_requires_ownership(
    client: TestClient, make_car, make_user
) -> None:
    car = make_car()
    other_headers = make_user(email="other@example.com")
    response = client.get(f"/api/cars/{car['id']}/analytics", headers=other_headers)
    assert response.status_code == 404


def test_analytics_requires_auth(client: TestClient, make_car) -> None:
    car = make_car()
    assert client.get(f"/api/cars/{car['id']}/analytics").status_code == 401
