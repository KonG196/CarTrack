"""Import tests: append semantics, transactional all-or-nothing, validation paths."""

import datetime as dt

from fastapi.testclient import TestClient

from tests.test_export import _seed_car_with_logs

TODAY = dt.date.today()


def _import_payload(**overrides) -> dict:
    payload = {
        "schema_version": 1,
        "cars": [
            {
                "brand": "Skoda",
                "model": "Octavia",
                "year": 2016,
                "fuel_type": "diesel",
                "current_odometer": 5000,
                "intervals": [
                    {"title": "Ремінь ГРМ", "interval_km": 60000, "last_odometer": 1000}
                ],
                "logs": [
                    {
                        "type": "expense",
                        "odometer": 4000,
                        "date": TODAY.isoformat(),
                        "total_cost": 10,
                        "notes": "Парковка",
                    }
                ],
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_round_trip_export_import_doubles_counts(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = _seed_car_with_logs(client, auth_headers, make_car)
    exported = client.get("/api/export", headers=auth_headers).json()

    response = client.post("/api/import", json=exported, headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "cars_created": 1,
        "logs_created": 4,
        "intervals_created": 1,
    }

    cars = client.get("/api/cars", headers=auth_headers).json()
    assert len(cars) == 2
    new_car = next(c for c in cars if c["id"] != car["id"])
    logs = client.get(f"/api/cars/{new_car['id']}/logs", headers=auth_headers).json()
    assert logs["total"] == 4
    intervals = client.get(
        f"/api/cars/{new_car['id']}/intervals", headers=auth_headers
    ).json()
    assert len(intervals) == 1

    # a second import appends again (v1 policy: no dedup)
    again = client.post("/api/import", json=exported, headers=auth_headers)
    assert again.status_code == 200
    assert len(client.get("/api/cars", headers=auth_headers).json()) == 3


def test_import_does_not_touch_existing_cars_odometer(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    existing = make_car(current_odometer=10000)
    payload = _import_payload()
    payload["cars"][0]["logs"][0]["odometer"] = 99999

    response = client.post("/api/import", json=payload, headers=auth_headers)
    assert response.status_code == 200, response.text

    fetched = client.get(f"/api/cars/{existing['id']}", headers=auth_headers)
    assert fetched.json()["current_odometer"] == 10000


def test_import_wrong_schema_version_422(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.post(
        "/api/import", json=_import_payload(schema_version=2), headers=auth_headers
    )
    assert response.status_code == 422
    assert len(client.get("/api/cars", headers=auth_headers).json()) == 0


def test_import_invalid_element_rolls_back_everything(
    client: TestClient, auth_headers: dict
) -> None:
    payload = _import_payload()
    payload["cars"][0]["logs"].append(
        {
            "type": "refuel",  # invalid: refuel details are required
            "odometer": 4100,
            "date": TODAY.isoformat(),
            "total_cost": 50,
        }
    )
    response = client.post("/api/import", json=payload, headers=auth_headers)
    assert response.status_code == 422
    assert "cars[0].logs[1]" in response.json()["detail"]
    # all-or-nothing: the valid car/interval/log must not have been created
    assert len(client.get("/api/cars", headers=auth_headers).json()) == 0


def test_import_garbage_json_422_without_partial_inserts(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.post(
        "/api/import",
        json={"schema_version": 1, "cars": [{"nonsense": True}]},
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert "cars[0]" in response.json()["detail"]
    assert len(client.get("/api/cars", headers=auth_headers).json()) == 0


def test_import_requires_auth(client: TestClient) -> None:
    assert client.post("/api/import", json=_import_payload()).status_code == 401
