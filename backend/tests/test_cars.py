"""Car CRUD, validation, avg_daily_km and per-user isolation tests."""

import datetime as dt

from fastapi.testclient import TestClient


def test_car_crud_roundtrip(client: TestClient, auth_headers: dict, make_car) -> None:
    car = make_car(brand="Skoda", model="Octavia", generation="III", engine="2.0 TDI")
    car_id = car["id"]
    assert car["brand"] == "Skoda"
    assert car["generation"] == "III"
    assert car["current_odometer"] == 10000

    listed = client.get("/api/cars", headers=auth_headers)
    assert listed.status_code == 200
    assert [c["id"] for c in listed.json()] == [car_id]

    fetched = client.get(f"/api/cars/{car_id}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["model"] == "Octavia"

    patched = client.patch(
        f"/api/cars/{car_id}",
        json={"current_odometer": 12000, "engine": "1.8 TSI"},
        headers=auth_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["current_odometer"] == 12000
    assert patched.json()["engine"] == "1.8 TSI"
    assert patched.json()["brand"] == "Skoda"

    deleted = client.delete(f"/api/cars/{car_id}", headers=auth_headers)
    assert deleted.status_code == 204

    assert client.get(f"/api/cars/{car_id}", headers=auth_headers).status_code == 404
    assert client.get("/api/cars", headers=auth_headers).json() == []


def test_avg_daily_km_defaults_to_40_without_logs(make_car) -> None:
    car = make_car()
    assert car["avg_daily_km"] == 40.0


def test_avg_daily_km_computed_from_logs(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    start = dt.date.today() - dt.timedelta(days=20)
    end = dt.date.today()
    for log_date, odometer in ((start, 10000), (end, 11000)):
        response = client.post(
            f"/api/cars/{car['id']}/logs",
            json={
                "type": "expense",
                "odometer": odometer,
                "date": log_date.isoformat(),
                "total_cost": 10,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text

    fetched = client.get(f"/api/cars/{car['id']}", headers=auth_headers)
    # 1000 km over 20 days -> 50 km/day
    assert fetched.json()["avg_daily_km"] == 50.0


def test_car_validation_422(client: TestClient, auth_headers: dict) -> None:
    base = {
        "brand": "VW",
        "model": "Golf",
        "year": 2015,
        "fuel_type": "diesel",
        "current_odometer": 100,
    }
    for bad_field, bad_value in (
        ("year", 1900),
        ("year", 2200),
        ("fuel_type", "coal"),
        ("current_odometer", -5),
        ("brand", ""),
    ):
        payload = dict(base)
        payload[bad_field] = bad_value
        response = client.post("/api/cars", json=payload, headers=auth_headers)
        assert response.status_code == 422, f"{bad_field}={bad_value}: {response.text}"


def test_cars_require_auth(client: TestClient) -> None:
    assert client.get("/api/cars").status_code == 401
    assert client.post("/api/cars", json={}).status_code == 401


def test_user_isolation_404(
    client: TestClient, auth_headers: dict, make_car, make_user
) -> None:
    car = make_car()
    other_headers = make_user(email="other@example.com")

    assert client.get(f"/api/cars/{car['id']}", headers=other_headers).status_code == 404
    assert (
        client.patch(
            f"/api/cars/{car['id']}", json={"brand": "Hacked"}, headers=other_headers
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/cars/{car['id']}", headers=other_headers).status_code == 404
    )
    assert client.get("/api/cars", headers=other_headers).json() == []

    # Owner still sees the untouched car.
    fetched = client.get(f"/api/cars/{car['id']}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["brand"] == "Toyota"
