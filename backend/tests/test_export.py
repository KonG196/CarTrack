"""Export tests: full JSON dump (no internal ids) and per-car CSV of logs."""

import csv
import datetime as dt
import io

from fastapi.testclient import TestClient

TODAY = dt.date.today()

FORBIDDEN_KEYS = {
    "id",
    "user_id",
    "car_id",
    "log_entry_id",
    "hashed_password",
    "telegram_chat_id",
    "reset_code_hash",
    "reset_code_expires_at",
}


def _seed_car_with_logs(client: TestClient, auth_headers: dict, make_car) -> dict:
    car = make_car(current_odometer=10000)
    logs = [
        {
            "type": "refuel",
            "odometer": 10100,
            "date": TODAY.isoformat(),
            "total_cost": 60.0,
            "refuel": {
                "liters": 40,
                "price_per_liter": 1.5,
                "is_full_tank": True,
                "gas_station": "ОККО",
            },
        },
        {
            "type": "maintenance",
            "odometer": 10200,
            "date": TODAY.isoformat(),
            "total_cost": 150.0,
            "maintenance": {
                "parts_cost": 100,
                "labor_cost": 50,
                "items": ["олива", "фільтр"],
            },
        },
        {
            "type": "repair",
            "odometer": 10300,
            "date": TODAY.isoformat(),
            "total_cost": 300.0,
            "notes": "Заміна гальм",
            "repair": {
                "category": "Гальма",
                "part_name": "Колодки",
                "warranty_months": 12,
                "warranty_km": 20000,
            },
        },
        {
            "type": "expense",
            "odometer": 10300,
            "date": TODAY.isoformat(),
            "total_cost": 25.0,
            "notes": "Мийка",
        },
    ]
    for payload in logs:
        response = client.post(
            f"/api/cars/{car['id']}/logs", json=payload, headers=auth_headers
        )
        assert response.status_code == 201, response.text
    response = client.post(
        f"/api/cars/{car['id']}/intervals",
        json={"title": "Олива двигуна", "interval_km": 10000, "last_odometer": 5000},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    return car


def _assert_no_forbidden_keys(node) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            assert key not in FORBIDDEN_KEYS, f"forbidden key '{key}' leaked into export"
            _assert_no_forbidden_keys(value)
    elif isinstance(node, list):
        for item in node:
            _assert_no_forbidden_keys(item)


def test_export_json_contains_all_entities(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    _seed_car_with_logs(client, auth_headers, make_car)

    response = client.get("/api/export", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert "attachment" in response.headers["content-disposition"]
    assert "kapot-tracker-export-" in response.headers["content-disposition"]

    body = response.json()
    assert body["schema_version"] == 2
    assert body["exported_at"]
    assert len(body["cars"]) == 1

    car = body["cars"][0]
    assert car["brand"] == "Toyota"
    assert car["current_odometer"] == 10300  # bumped by the seeded logs
    assert len(car["logs"]) == 4
    assert len(car["intervals"]) == 1
    assert car["intervals"][0]["title"] == "Олива двигуна"

    by_type = {log["type"]: log for log in car["logs"]}
    assert by_type["refuel"]["refuel"]["liters"] == 40.0
    assert by_type["maintenance"]["maintenance"]["items"] == ["олива", "фільтр"]
    assert by_type["repair"]["repair"]["category"] == "Гальма"
    assert by_type["expense"]["notes"] == "Мийка"


def test_export_json_leaks_no_internal_ids(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    _seed_car_with_logs(client, auth_headers, make_car)
    body = client.get("/api/export", headers=auth_headers).json()
    _assert_no_forbidden_keys(body)


def test_export_requires_auth(client: TestClient) -> None:
    assert client.get("/api/export").status_code == 401


def test_export_csv_has_bom_and_one_row_per_log(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = _seed_car_with_logs(client, auth_headers, make_car)

    response = client.get(f"/api/cars/{car['id']}/export.csv", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.startswith(b"\xef\xbb\xbf")  # utf-8-sig BOM for Excel

    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(rows) == 5  # header + 4 logs
    assert rows[0] == [
        "date",
        "type",
        "odometer",
        "total_cost",
        "liters",
        "price_per_liter",
        "is_full_tank",
        "gas_station",
        "items",
        "parts_cost",
        "labor_cost",
        "category",
        "part_name",
        "warranty_months",
        "warranty_km",
        "notes",
    ]
    by_type = {row[1]: row for row in rows[1:]}
    assert by_type["refuel"][4] == "40.0"
    assert by_type["maintenance"][8] == "олива; фільтр"
    assert by_type["repair"][11] == "Гальма"


def test_export_csv_foreign_car_404(
    client: TestClient, auth_headers: dict, make_car, make_user
) -> None:
    car = make_car()
    stranger = make_user(email="stranger@example.com")
    response = client.get(f"/api/cars/{car['id']}/export.csv", headers=stranger)
    assert response.status_code == 404
