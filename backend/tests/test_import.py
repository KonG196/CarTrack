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
        "specs_created": 0,
        "tire_sets_created": 0,
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
        "/api/import", json=_import_payload(schema_version=99), headers=auth_headers
    )
    assert response.status_code == 422
    assert len(client.get("/api/cars", headers=auth_headers).json()) == 0


def test_v1_dump_still_imports(client: TestClient, auth_headers: dict) -> None:
    # A pre-v2 dump (no specs/tire_sets, no config scalars) must still import.
    response = client.post("/api/import", json=_import_payload(), headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cars_created"] == 1
    assert body["specs_created"] == 0 and body["tire_sets_created"] == 0


def test_v2_round_trip_preserves_config_specs_and_tires(
    client: TestClient, auth_headers: dict
) -> None:
    car = client.post(
        "/api/cars",
        json={
            "brand": "VW", "model": "Passat", "year": 2016, "fuel_type": "diesel",
            "current_odometer": 168000, "vin": "WVWZZZ3CZGE000001", "plate": "AA1234BB",
            "monthly_budget": 15000, "insurance_until": "2027-03-01", "tank_liters": 66,
        },
        headers=auth_headers,
    ).json()
    client.post(
        f"/api/cars/{car['id']}/specs",
        json={"category": "Моменти затяжки", "name": "Колісні болти", "value": "120 Нм"},
        headers=auth_headers,
    )
    tire = client.post(
        f"/api/cars/{car['id']}/tires",
        json={"name": "Зима Nokian", "season": "winter", "size": "215/55 R17", "dot_year": 2022},
        headers=auth_headers,
    ).json()
    client.post(f"/api/tires/{tire['id']}/install", headers=auth_headers)

    exported = client.get("/api/export", headers=auth_headers).json()
    assert exported["schema_version"] == 2
    result = client.post("/api/import", json=exported, headers=auth_headers).json()
    assert result["specs_created"] == 1
    assert result["tire_sets_created"] == 1

    cars = client.get("/api/cars", headers=auth_headers).json()
    new_car = next(c for c in cars if c["id"] != car["id"])
    assert new_car["vin"] == "WVWZZZ3CZGE000001"
    assert new_car["plate"] == "AA1234BB"
    assert new_car["monthly_budget"] == 15000
    assert new_car["insurance_until"] == "2027-03-01"

    specs = client.get(f"/api/cars/{new_car['id']}/specs", headers=auth_headers).json()
    assert any(s["name"] == "Колісні болти" and s["value"] == "120 Нм" for s in specs)
    tires = client.get(f"/api/cars/{new_car['id']}/tires", headers=auth_headers).json()
    assert len(tires) == 1
    assert tires[0]["is_installed"] is True
    assert tires[0]["dot_year"] == 2022


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


def test_round_trip_preserves_expense_category_and_fuel_kind(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """An export→import must not collapse a categorized expense to the default
    or lose a refuel's fuel_kind (ГБО), which the analytics depend on."""
    car = make_car(current_odometer=10000)
    client.post(
        f"/api/cars/{car['id']}/logs",
        json={
            "type": "expense",
            "odometer": 10100,
            "date": "2026-07-01",
            "total_cost": 500,
            "expense": {"category": "Мийка"},
        },
        headers=auth_headers,
    )
    client.post(
        f"/api/cars/{car['id']}/logs",
        json={
            "type": "refuel",
            "odometer": 10200,
            "date": "2026-07-02",
            "total_cost": 900,
            "refuel": {
                "liters": 40,
                "price_per_liter": 22.5,
                "is_full_tank": True,
                "fuel_kind": "lpg",
            },
        },
        headers=auth_headers,
    )

    exported = client.get("/api/export", headers=auth_headers).json()
    # The export itself must carry the fields.
    logs = exported["cars"][0]["logs"]
    exp = next(l for l in logs if l["type"] == "expense")
    ref = next(l for l in logs if l["type"] == "refuel")
    assert exp["expense"]["category"] == "Мийка"
    assert ref["refuel"]["fuel_kind"] == "lpg"

    assert client.post("/api/import", json=exported, headers=auth_headers).status_code == 200
    cars = client.get("/api/cars", headers=auth_headers).json()
    new_car = next(c for c in cars if c["id"] != car["id"])
    new_logs = client.get(f"/api/cars/{new_car['id']}/logs", headers=auth_headers).json()["items"]
    new_exp = next(l for l in new_logs if l["type"] == "expense")
    new_ref = next(l for l in new_logs if l["type"] == "refuel")
    assert new_exp["expense"]["category"] == "Мийка"
    assert new_ref["refuel"]["fuel_kind"] == "lpg"


def test_import_requires_auth(client: TestClient) -> None:
    assert client.post("/api/import", json=_import_payload()).status_code == 401
