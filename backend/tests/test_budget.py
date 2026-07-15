"""Monthly budget: the monthly_budget car field and analytics.budget.

The budget block reports what the car already spent this calendar month
against the owner's limit, plus the month-end projection the forecast
already computes — the two numbers must never disagree.
"""

import datetime as dt

from fastapi.testclient import TestClient

TODAY = dt.date.today()


def _spend(client: TestClient, headers: dict, car_id: int, amount: float) -> None:
    response = client.post(
        f"/api/cars/{car_id}/logs",
        json={
            "type": "expense",
            "odometer": 10000,
            "date": TODAY.isoformat(),
            "total_cost": amount,
            "notes": "паркування",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text


def _budget(client: TestClient, headers: dict, car_id: int) -> dict | None:
    response = client.get(f"/api/cars/{car_id}/analytics", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["budget"]


# The car field


def test_car_monthly_budget_defaults_to_null(make_car) -> None:
    assert make_car()["monthly_budget"] is None


def test_car_stores_and_clears_the_monthly_budget(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(monthly_budget=5000)
    assert car["monthly_budget"] == 5000.0

    patched = client.patch(
        f"/api/cars/{car['id']}", json={"monthly_budget": 7500.50}, headers=auth_headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["monthly_budget"] == 7500.50

    cleared = client.patch(
        f"/api/cars/{car['id']}", json={"monthly_budget": None}, headers=auth_headers
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["monthly_budget"] is None


def test_car_rejects_a_non_positive_budget_422(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    for bad in (0, -100):
        response = client.patch(
            f"/api/cars/{car['id']}", json={"monthly_budget": bad}, headers=auth_headers
        )
        assert response.status_code == 422, f"{bad}: {response.text}"


# analytics.budget


def test_budget_is_null_without_a_limit(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    _spend(client, auth_headers, car["id"], 500)
    assert _budget(client, auth_headers, car["id"]) is None


def test_budget_shape_and_spend(client: TestClient, auth_headers: dict, make_car) -> None:
    car = make_car(monthly_budget=5000)
    _spend(client, auth_headers, car["id"], 1200)

    budget = _budget(client, auth_headers, car["id"])
    assert set(budget.keys()) == {
        "limit",
        "spent_this_month",
        "projected_month_total",
        "pct_used",
        "status",
    }
    assert budget["limit"] == 5000.0
    assert budget["spent_this_month"] == 1200.0
    assert budget["pct_used"] == 24.0
    assert budget["status"] == "ok"


def test_budget_spend_matches_the_month_total(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(monthly_budget=5000)
    _spend(client, auth_headers, car["id"], 1200)

    body = client.get(f"/api/cars/{car['id']}/analytics", headers=auth_headers).json()
    assert body["budget"]["spent_this_month"] == body["totals"]["this_month"]


def test_budget_projection_is_the_forecast_projection(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(monthly_budget=5000)
    _spend(client, auth_headers, car["id"], 1200)

    body = client.get(f"/api/cars/{car['id']}/analytics", headers=auth_headers).json()
    forecast = body["forecast"]["projected_month_total"]
    assert forecast is not None
    assert body["budget"]["projected_month_total"] == forecast


def test_budget_projection_is_null_when_the_forecast_has_none(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """No spending data at all: a limit still renders, a projection cannot."""
    car = make_car(monthly_budget=5000)

    body = client.get(f"/api/cars/{car['id']}/analytics", headers=auth_headers).json()
    assert body["forecast"]["projected_month_total"] is None
    assert body["budget"]["projected_month_total"] is None
    assert body["budget"]["spent_this_month"] == 0.0
    assert body["budget"]["pct_used"] == 0.0
    assert body["budget"]["status"] == "ok"


def test_budget_status_thresholds(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    cases = (
        (3999, "ok"),  # 79.98%
        (4000, "warn"),  # exactly 80% — the warning starts here
        (4999, "warn"),
        (5000, "warn"),  # exactly at the limit is not yet over it
        (5001, "over"),
        (7500, "over"),
    )
    for index, (amount, expected) in enumerate(cases):
        car = make_car(monthly_budget=5000)
        _spend(client, auth_headers, car["id"], amount)
        budget = _budget(client, auth_headers, car["id"])
        assert budget["status"] == expected, f"{amount} ₴ -> {budget}"
        assert budget["pct_used"] == round(amount / 5000 * 100, 1), index
