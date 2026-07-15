"""Per-refuel consumption in the log list: full-to-full mapping and query count."""

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import event

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
            },
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _seed_full_partial_full(client: TestClient, headers: dict, car_id: int) -> dict:
    return {
        "anchor": _refuel(client, headers, car_id, 10000, 40, True, days_ago=30),
        "partial": _refuel(client, headers, car_id, 10400, 20, False, days_ago=20),
        "closing": _refuel(client, headers, car_id, 10800, 25, True, days_ago=10),
    }


def test_consumption_only_on_the_closing_full_refuel(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    seeded = _seed_full_partial_full(client, auth_headers, car["id"])

    listed = client.get(f"/api/cars/{car['id']}/logs", headers=auth_headers)
    assert listed.status_code == 200
    by_id = {item["id"]: item for item in listed.json()["items"]}

    # 45 L over 800 km -> 5.625 l/100km (~5.63), on the closing full tank only.
    closing = by_id[seeded["closing"]["id"]]["refuel"]
    assert closing["consumption_l_100km"] is not None
    assert abs(closing["consumption_l_100km"] - 5.625) <= 0.02

    # The opening anchor has no preceding full tank; the partial closes nothing.
    assert by_id[seeded["anchor"]["id"]]["refuel"]["consumption_l_100km"] is None
    assert by_id[seeded["partial"]["id"]]["refuel"]["consumption_l_100km"] is None


def test_consumption_matches_the_analytics_history(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    seeded = _seed_full_partial_full(client, auth_headers, car["id"])

    fuel = client.get(f"/api/cars/{car['id']}/analytics", headers=auth_headers).json()["fuel"]
    assert len(fuel["history"]) == 1
    segment = fuel["history"][0]

    detail = client.get(f"/api/logs/{seeded['closing']['id']}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["refuel"]["consumption_l_100km"] == segment["consumption_l_100km"]


def test_single_log_detail_exposes_consumption(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    seeded = _seed_full_partial_full(client, auth_headers, car["id"])

    for key, expected_none in (("anchor", True), ("partial", True), ("closing", False)):
        response = client.get(f"/api/logs/{seeded[key]['id']}", headers=auth_headers)
        assert response.status_code == 200, response.text
        value = response.json()["refuel"]["consumption_l_100km"]
        assert (value is None) is expected_none, key


def test_non_refuel_logs_have_no_refuel_detail(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    response = client.post(
        f"/api/cars/{car['id']}/logs",
        json={
            "type": "expense",
            "odometer": 10100,
            "date": TODAY.isoformat(),
            "total_cost": 50,
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    listed = client.get(f"/api/cars/{car['id']}/logs", headers=auth_headers)
    assert listed.json()["items"][0]["refuel"] is None


def test_type_filtered_list_keeps_whole_car_segments(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    seeded = _seed_full_partial_full(client, auth_headers, car["id"])

    listed = client.get(
        f"/api/cars/{car['id']}/logs",
        params={"type": "refuel", "limit": 1},
        headers=auth_headers,
    )
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == seeded["closing"]["id"]
    assert abs(items[0]["refuel"]["consumption_l_100km"] - 5.625) <= 0.02


def test_consumption_is_isolated_per_car(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """Another car's refuels must not close this car's segments."""
    first = make_car(current_odometer=10000)
    second = make_car(current_odometer=10000)
    _seed_full_partial_full(client, auth_headers, first["id"])
    lonely = _refuel(client, auth_headers, second["id"], 10800, 25, True, days_ago=10)

    listed = client.get(f"/api/cars/{second['id']}/logs", headers=auth_headers)
    by_id = {item["id"]: item for item in listed.json()["items"]}
    assert by_id[lonely["id"]]["refuel"]["consumption_l_100km"] is None


def test_patch_response_carries_the_recomputed_consumption(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """PATCH declares LogEntryOut, so it must fill the same segment field GET does.

    The edit re-opens the segment: halving the closing liters halves the
    reported consumption, and the client renders the response it got back.
    """
    car = make_car(current_odometer=10000)
    seeded = _seed_full_partial_full(client, auth_headers, car["id"])

    patched = client.patch(
        f"/api/logs/{seeded['closing']['id']}",
        json={"refuel": {"liters": 10}},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text

    # 30 L (20 partial + 10) over 800 km -> 3.75 l/100km.
    value = patched.json()["refuel"]["consumption_l_100km"]
    assert value is not None
    assert abs(value - 3.75) <= 0.02

    fetched = client.get(f"/api/logs/{seeded['closing']['id']}", headers=auth_headers)
    assert fetched.json()["refuel"]["consumption_l_100km"] == value


def test_create_response_carries_the_closed_segment_consumption(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    _refuel(client, auth_headers, car["id"], 10000, 40, True, days_ago=30)
    created = _refuel(client, auth_headers, car["id"], 10800, 45, True, days_ago=10)

    assert created["refuel"]["consumption_l_100km"] is not None
    assert abs(created["refuel"]["consumption_l_100km"] - 5.625) <= 0.02


def test_log_list_query_count_does_not_scale_with_logs(
    client: TestClient, auth_headers: dict, make_car, db_engine
) -> None:
    """The segment map must be built once per request, never per row (N+1)."""
    counts: list[int] = []
    for n_logs in (2, 12):
        car = make_car(current_odometer=30000)
        for i in range(n_logs):
            _refuel(
                client,
                auth_headers,
                car["id"],
                odometer=10000 + i * 400,
                liters=40,
                is_full_tank=True,
                days_ago=n_logs - i,
            )

        statements: list[str] = []

        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(db_engine, "before_cursor_execute", before_cursor_execute)
        try:
            response = client.get(f"/api/cars/{car['id']}/logs", headers=auth_headers)
        finally:
            event.remove(db_engine, "before_cursor_execute", before_cursor_execute)
        assert response.status_code == 200
        counts.append(len(statements))

    assert counts[0] == counts[1], f"query count grew with log count: {counts}"
