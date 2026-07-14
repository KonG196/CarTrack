"""Log entry tests: creation side effects, detail validation, CRUD, isolation."""

import datetime as dt

from fastapi.testclient import TestClient

TODAY = dt.date.today()


def _refuel_payload(odometer: int, **overrides) -> dict:
    payload = {
        "type": "refuel",
        "odometer": odometer,
        "date": TODAY.isoformat(),
        "total_cost": 60.0,
        "refuel": {
            "liters": 40,
            "price_per_liter": 1.5,
            "is_full_tank": True,
            "gas_station": "Shell",
        },
    }
    payload.update(overrides)
    return payload


def test_create_log_updates_car_odometer(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    response = client.post(
        f"/api/cars/{car['id']}/logs",
        json=_refuel_payload(10500),
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["type"] == "refuel"
    assert body["car_id"] == car["id"]
    assert body["refuel"]["liters"] == 40.0
    assert body["refuel"]["is_full_tank"] is True
    assert body["maintenance"] is None
    assert body["repair"] is None

    fetched = client.get(f"/api/cars/{car['id']}", headers=auth_headers)
    assert fetched.json()["current_odometer"] == 10500


def test_create_log_with_lower_odometer_keeps_car_odometer(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    response = client.post(
        f"/api/cars/{car['id']}/logs",
        json=_refuel_payload(9000),
        headers=auth_headers,
    )
    assert response.status_code == 201
    fetched = client.get(f"/api/cars/{car['id']}", headers=auth_headers)
    assert fetched.json()["current_odometer"] == 10000


def test_refuel_without_detail_422(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    payload = _refuel_payload(10500)
    del payload["refuel"]
    response = client.post(
        f"/api/cars/{car['id']}/logs", json=payload, headers=auth_headers
    )
    assert response.status_code == 422


def test_maintenance_without_detail_422(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    response = client.post(
        f"/api/cars/{car['id']}/logs",
        json={
            "type": "maintenance",
            "odometer": 10100,
            "date": TODAY.isoformat(),
            "total_cost": 150,
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_repair_detail_is_optional(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    without_detail = client.post(
        f"/api/cars/{car['id']}/logs",
        json={
            "type": "repair",
            "odometer": 10100,
            "date": TODAY.isoformat(),
            "total_cost": 80,
        },
        headers=auth_headers,
    )
    assert without_detail.status_code == 201
    assert without_detail.json()["repair"] is None

    with_detail = client.post(
        f"/api/cars/{car['id']}/logs",
        json={
            "type": "repair",
            "odometer": 10200,
            "date": TODAY.isoformat(),
            "total_cost": 120,
            "repair": {"category": "brakes", "part_name": "front pads", "warranty_months": 24},
        },
        headers=auth_headers,
    )
    assert with_detail.status_code == 201
    assert with_detail.json()["repair"]["category"] == "brakes"


def test_list_logs_filter_sort_and_pagination(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    entries = [
        ("expense", 10100, TODAY - dt.timedelta(days=3)),
        ("refuel", 10200, TODAY - dt.timedelta(days=2)),
        ("expense", 10300, TODAY - dt.timedelta(days=1)),
        ("expense", 10400, TODAY),
    ]
    for log_type, odometer, log_date in entries:
        payload = {
            "type": log_type,
            "odometer": odometer,
            "date": log_date.isoformat(),
            "total_cost": 10,
        }
        if log_type == "refuel":
            payload["refuel"] = {"liters": 30, "price_per_liter": 1.5, "is_full_tank": True}
        response = client.post(
            f"/api/cars/{car['id']}/logs", json=payload, headers=auth_headers
        )
        assert response.status_code == 201, response.text

    all_logs = client.get(f"/api/cars/{car['id']}/logs", headers=auth_headers)
    assert all_logs.status_code == 200
    body = all_logs.json()
    assert body["total"] == 4
    # date desc, then odometer desc
    assert [item["odometer"] for item in body["items"]] == [10400, 10300, 10200, 10100]

    filtered = client.get(
        f"/api/cars/{car['id']}/logs", params={"type": "expense"}, headers=auth_headers
    )
    assert filtered.json()["total"] == 3
    assert all(item["type"] == "expense" for item in filtered.json()["items"])

    page = client.get(
        f"/api/cars/{car['id']}/logs",
        params={"limit": 2, "offset": 1},
        headers=auth_headers,
    )
    assert page.json()["total"] == 4
    assert [item["odometer"] for item in page.json()["items"]] == [10300, 10200]


def test_patch_log_shared_fields_and_detail(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    created = client.post(
        f"/api/cars/{car['id']}/logs",
        json=_refuel_payload(10500),
        headers=auth_headers,
    )
    log_id = created.json()["id"]

    patched = client.patch(
        f"/api/logs/{log_id}",
        json={"total_cost": 65.5, "notes": "highway trip", "refuel": {"liters": 42}},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["total_cost"] == 65.5
    assert body["notes"] == "highway trip"
    assert body["refuel"]["liters"] == 42.0
    # untouched detail fields are preserved
    assert body["refuel"]["price_per_liter"] == 1.5


def test_patch_log_odometer_side_effect_on_car(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """PATCHing a log ahead of the car bumps the car, like creation does.

    Lowering the log's odometer afterwards (or deleting it) must never
    move the car's odometer backwards.
    """
    car = make_car(current_odometer=10000)
    created = client.post(
        f"/api/cars/{car['id']}/logs",
        json=_refuel_payload(10500),
        headers=auth_headers,
    )
    log_id = created.json()["id"]
    assert (
        client.get(f"/api/cars/{car['id']}", headers=auth_headers).json()["current_odometer"]
        == 10500
    )

    # Correcting the log upwards must move the car forward too.
    patched = client.patch(
        f"/api/logs/{log_id}", json={"odometer": 12000}, headers=auth_headers
    )
    assert patched.status_code == 200, patched.text
    assert (
        client.get(f"/api/cars/{car['id']}", headers=auth_headers).json()["current_odometer"]
        == 12000
    )

    # Correcting the log downwards must NOT decrease the car's odometer.
    patched = client.patch(
        f"/api/logs/{log_id}", json={"odometer": 9000}, headers=auth_headers
    )
    assert patched.status_code == 200, patched.text
    assert (
        client.get(f"/api/cars/{car['id']}", headers=auth_headers).json()["current_odometer"]
        == 12000
    )

    # Deleting the log must NOT decrease the car's odometer either.
    assert client.delete(f"/api/logs/{log_id}", headers=auth_headers).status_code == 204
    assert (
        client.get(f"/api/cars/{car['id']}", headers=auth_headers).json()["current_odometer"]
        == 12000
    )


def test_delete_log(client: TestClient, auth_headers: dict, make_car) -> None:
    car = make_car()
    created = client.post(
        f"/api/cars/{car['id']}/logs",
        json=_refuel_payload(10500),
        headers=auth_headers,
    )
    log_id = created.json()["id"]

    assert client.delete(f"/api/logs/{log_id}", headers=auth_headers).status_code == 204
    listed = client.get(f"/api/cars/{car['id']}/logs", headers=auth_headers)
    assert listed.json()["total"] == 0
    assert client.delete(f"/api/logs/{log_id}", headers=auth_headers).status_code == 404


def test_log_ownership_isolation(
    client: TestClient, auth_headers: dict, make_car, make_user
) -> None:
    car = make_car()
    created = client.post(
        f"/api/cars/{car['id']}/logs",
        json=_refuel_payload(10500),
        headers=auth_headers,
    )
    log_id = created.json()["id"]

    other_headers = make_user(email="intruder@example.com")
    assert (
        client.get(f"/api/cars/{car['id']}/logs", headers=other_headers).status_code == 404
    )
    assert (
        client.post(
            f"/api/cars/{car['id']}/logs",
            json=_refuel_payload(11000),
            headers=other_headers,
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/logs/{log_id}", json={"notes": "stolen"}, headers=other_headers
        ).status_code
        == 404
    )
    assert client.delete(f"/api/logs/{log_id}", headers=other_headers).status_code == 404
