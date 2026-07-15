"""Logbook search (?q=) across notes and detail fields, plus single-log GET."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

TODAY = dt.date.today()


@pytest.fixture()
def seeded_car(client: TestClient, auth_headers: dict, make_car) -> dict:
    car = make_car()
    entries = [
        {
            "type": "refuel",
            "odometer": 10100,
            "date": TODAY.isoformat(),
            "total_cost": 60,
            "refuel": {
                "liters": 40,
                "price_per_liter": 1.5,
                "is_full_tank": True,
                "gas_station": "WOG Kyiv",
            },
        },
        {
            "type": "maintenance",
            "odometer": 10200,
            "date": TODAY.isoformat(),
            "total_cost": 150,
            "maintenance": {
                "parts_cost": 100,
                "labor_cost": 50,
                "items": ["Фільтр повітряний", "Олива моторна"],
            },
        },
        {
            "type": "repair",
            "odometer": 10300,
            "date": TODAY.isoformat(),
            "total_cost": 200,
            "repair": {"category": "Гальма", "part_name": "колодки передні"},
        },
        {
            "type": "expense",
            "odometer": 10400,
            "date": TODAY.isoformat(),
            "total_cost": 20,
            "notes": "мийка та пилосос",
        },
    ]
    for payload in entries:
        response = client.post(
            f"/api/cars/{car['id']}/logs", json=payload, headers=auth_headers
        )
        assert response.status_code == 201, response.text
    return car


def _search(client: TestClient, headers: dict, car_id: int, **params) -> dict:
    response = client.get(f"/api/cars/{car_id}/logs", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_search_by_notes(client: TestClient, auth_headers: dict, seeded_car: dict) -> None:
    body = _search(client, auth_headers, seeded_car["id"], q="мийка")
    assert body["total"] == 1
    assert body["items"][0]["type"] == "expense"


def test_search_by_maintenance_items(
    client: TestClient, auth_headers: dict, seeded_car: dict
) -> None:
    body = _search(client, auth_headers, seeded_car["id"], q="Фільтр")
    assert body["total"] == 1
    assert body["items"][0]["type"] == "maintenance"


def test_search_by_repair_category_and_part(
    client: TestClient, auth_headers: dict, seeded_car: dict
) -> None:
    by_category = _search(client, auth_headers, seeded_car["id"], q="Гальма")
    assert by_category["total"] == 1
    assert by_category["items"][0]["type"] == "repair"

    by_part = _search(client, auth_headers, seeded_car["id"], q="колодки")
    assert by_part["total"] == 1
    assert by_part["items"][0]["type"] == "repair"


def test_search_by_gas_station(
    client: TestClient, auth_headers: dict, seeded_car: dict
) -> None:
    body = _search(client, auth_headers, seeded_car["id"], q="WOG")
    assert body["total"] == 1
    assert body["items"][0]["type"] == "refuel"


def test_search_is_case_insensitive_for_latin(
    client: TestClient, auth_headers: dict, seeded_car: dict
) -> None:
    for query in ("wog", "WOG", "Wog"):
        body = _search(client, auth_headers, seeded_car["id"], q=query)
        assert body["total"] == 1, query


def test_search_combines_with_type_filter(
    client: TestClient, auth_headers: dict, seeded_car: dict
) -> None:
    # "о" is present in maintenance items, repair part_name and expense notes;
    # the type filter must narrow the match down to a single entry.
    matching_type = _search(client, auth_headers, seeded_car["id"], q="колодки", type="repair")
    assert matching_type["total"] == 1
    assert matching_type["items"][0]["type"] == "repair"

    other_type = _search(client, auth_headers, seeded_car["id"], q="колодки", type="refuel")
    assert other_type["total"] == 0
    assert other_type["items"] == []


def test_search_without_matches(
    client: TestClient, auth_headers: dict, seeded_car: dict
) -> None:
    body = _search(client, auth_headers, seeded_car["id"], q="немаєтакого")
    assert body["total"] == 0
    assert body["items"] == []


def test_search_keeps_total_consistent_with_pagination(
    client: TestClient, auth_headers: dict, seeded_car: dict
) -> None:
    # "о" appears in several entries; total must count all matches even when
    # limit trims the page.
    full = _search(client, auth_headers, seeded_car["id"], q="о")
    paged = _search(client, auth_headers, seeded_car["id"], q="о", limit=1)
    assert full["total"] >= 2
    assert paged["total"] == full["total"]
    assert len(paged["items"]) == 1


def test_get_single_log(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    created = client.post(
        f"/api/cars/{car['id']}/logs",
        json={
            "type": "repair",
            "odometer": 10300,
            "date": TODAY.isoformat(),
            "total_cost": 200,
            "notes": "СТО на Позняках",
            "repair": {"category": "Гальма", "part_name": "колодки"},
        },
        headers=auth_headers,
    )
    log_id = created.json()["id"]

    response = client.get(f"/api/logs/{log_id}", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == log_id
    assert body["car_id"] == car["id"]
    assert body["repair"]["category"] == "Гальма"
    assert body["notes"] == "СТО на Позняках"
    assert body["photos"] == []


def test_get_single_log_ownership_404(
    client: TestClient, auth_headers: dict, make_car, make_user
) -> None:
    car = make_car()
    created = client.post(
        f"/api/cars/{car['id']}/logs",
        json={
            "type": "expense",
            "odometer": 10100,
            "date": TODAY.isoformat(),
            "total_cost": 20,
        },
        headers=auth_headers,
    )
    log_id = created.json()["id"]

    other_headers = make_user(email="intruder@example.com")
    assert client.get(f"/api/logs/{log_id}", headers=other_headers).status_code == 404
    assert client.get("/api/logs/999999", headers=auth_headers).status_code == 404
