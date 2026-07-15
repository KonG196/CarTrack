"""Interval preset catalogue: maintenance + Ukrainian compliance groups."""

from fastapi.testclient import TestClient


def test_presets_endpoint_shape(client: TestClient, auth_headers: dict) -> None:
    response = client.get("/api/interval-presets", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"maintenance", "compliance"}
    assert body["maintenance"] and body["compliance"]
    for group in body.values():
        for item in group:
            assert set(item) == {"title", "interval_km", "interval_days"}
            assert item["title"]
            # Every preset is usable as a ServiceIntervalCreate payload.
            assert item["interval_km"] is not None or item["interval_days"] is not None


def test_maintenance_presets_match_the_known_set(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.get("/api/interval-presets", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["maintenance"] == [
        {"title": "Олива двигуна", "interval_km": 10000, "interval_days": 365},
        {"title": "Повітряний фільтр", "interval_km": 20000, "interval_days": None},
        {"title": "Паливний фільтр", "interval_km": 30000, "interval_days": None},
        {"title": "Салонний фільтр", "interval_km": 15000, "interval_days": 365},
        {"title": "ГРМ", "interval_km": 120000, "interval_days": None},
        {"title": "Гальмівна рідина", "interval_km": 60000, "interval_days": 730},
    ]


def test_compliance_presets_are_date_only(client: TestClient, auth_headers: dict) -> None:
    response = client.get("/api/interval-presets", headers=auth_headers)
    assert response.status_code == 200, response.text
    compliance = response.json()["compliance"]
    for item in compliance:
        assert item["interval_km"] is None, item
        assert item["interval_days"] is not None, item
    assert compliance == [
        {"title": "Поліс ОСЦПВ", "interval_km": None, "interval_days": 365},
        {"title": "Техогляд", "interval_km": None, "interval_days": 730},
        {"title": "Зелена карта", "interval_km": None, "interval_days": 365},
        {"title": "Транспортний податок", "interval_km": None, "interval_days": 365},
    ]


def test_presets_require_auth(client: TestClient) -> None:
    response = client.get("/api/interval-presets")
    assert response.status_code == 401


def test_compliance_preset_is_accepted_by_interval_create(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    preset = client.get("/api/interval-presets", headers=auth_headers).json()[
        "compliance"
    ][0]
    response = client.post(
        f"/api/cars/{car['id']}/intervals",
        json={**preset, "last_date": "2026-01-10"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["title"] == preset["title"]
    assert created["interval_km"] is None
    assert created["km_left"] is None
    assert created["due_date"] == "2027-01-10"
