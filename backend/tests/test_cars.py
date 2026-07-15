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


# avg_daily_km: computed value, manual override, effective value


def _add_log(client: TestClient, headers: dict, car_id: int, day: dt.date, odo: int) -> None:
    response = client.post(
        f"/api/cars/{car_id}/logs",
        json={
            "type": "expense",
            "odometer": odo,
            "date": day.isoformat(),
            "total_cost": 10,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text


def test_car_reports_computed_and_override_alongside_the_effective_value(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    _add_log(client, auth_headers, car["id"], dt.date.today() - dt.timedelta(days=20), 10000)
    _add_log(client, auth_headers, car["id"], dt.date.today(), 11000)

    body = client.get(f"/api/cars/{car['id']}", headers=auth_headers).json()
    assert body["avg_daily_km"] == 50.0  # effective
    assert body["avg_daily_km_computed"] == 50.0
    assert body["avg_daily_km_override"] is None


def test_avg_daily_km_override_wins_over_the_computed_value(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10000)
    _add_log(client, auth_headers, car["id"], dt.date.today() - dt.timedelta(days=20), 10000)
    _add_log(client, auth_headers, car["id"], dt.date.today(), 11000)

    patched = client.patch(
        f"/api/cars/{car['id']}", json={"avg_daily_km_override": 12.5}, headers=auth_headers
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["avg_daily_km"] == 12.5  # the override is the effective value
    assert body["avg_daily_km_override"] == 12.5
    assert body["avg_daily_km_computed"] == 50.0  # still reported for the hint

    # Clearing it hands the car back to auto mode.
    cleared = client.patch(
        f"/api/cars/{car['id']}", json={"avg_daily_km_override": None}, headers=auth_headers
    )
    assert cleared.json()["avg_daily_km_override"] is None
    assert cleared.json()["avg_daily_km"] == 50.0


def test_avg_daily_km_override_drives_the_interval_forecast(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """The override exists to fix wrong ТО dates, so it must reach them."""
    car = make_car(current_odometer=50000)
    response = client.post(
        f"/api/cars/{car['id']}/intervals",
        json={"title": "Олива двигуна", "interval_km": 10000, "last_odometer": 45000},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    # No logs -> the 40 km/day default: 5000 km left -> 125 days.
    assert response.json()["predicted_due_date"] == (
        dt.date.today() + dt.timedelta(days=125)
    ).isoformat()

    client.patch(f"/api/cars/{car['id']}", json={"avg_daily_km_override": 100}, headers=auth_headers)

    listed = client.get(f"/api/cars/{car['id']}/intervals", headers=auth_headers).json()
    # 5000 km at the overridden 100 km/day -> 50 days.
    assert listed[0]["predicted_due_date"] == (
        dt.date.today() + dt.timedelta(days=50)
    ).isoformat()


def test_avg_daily_km_override_validation_422(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    for bad in (0, -5):
        response = client.patch(
            f"/api/cars/{car['id']}",
            json={"avg_daily_km_override": bad},
            headers=auth_headers,
        )
        assert response.status_code == 422, f"{bad}: {response.text}"


# VIN and plate

GOLF_VIN = "WVWZZZAUZHP541983"


def test_car_stores_vin_and_plate_normalized(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(vin=GOLF_VIN.lower(), plate=" ae 1234 ao ")
    assert car["vin"] == GOLF_VIN
    assert car["plate"] == "AE 1234 AO"  # kept as typed, just trimmed and upcased

    patched = client.patch(
        f"/api/cars/{car['id']}", json={"plate": "АА0001АА"}, headers=auth_headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["plate"] == "АА0001АА"  # cyrillic plates pass through


def test_car_vin_and_plate_default_to_null(make_car) -> None:
    car = make_car()
    assert car["vin"] is None
    assert car["plate"] is None


def test_car_vin_can_be_cleared(client: TestClient, auth_headers: dict, make_car) -> None:
    car = make_car(vin=GOLF_VIN)
    for empty in ("", "   ", None):
        patched = client.patch(
            f"/api/cars/{car['id']}", json={"vin": empty}, headers=auth_headers
        )
        assert patched.status_code == 200, f"{empty!r}: {patched.text}"
        assert patched.json()["vin"] is None


def test_car_rejects_a_malformed_vin_422(client: TestClient, auth_headers: dict) -> None:
    base = {
        "brand": "VW",
        "model": "Golf",
        "year": 2017,
        "fuel_type": "diesel",
        "current_odometer": 240000,
    }
    for bad_vin in (
        "WVWZZZAUZHP54198",  # 16 chars
        "WVWZZZAUZHP5419833",  # 18 chars
        "WVWZZZAUZHP54198I",  # I, O, Q are not VIN characters
        "WVWZZZAUZHP54198O",
        "WVWZZZAUZHP54198Q",
        "WVWZZZAUZHP-41983",
    ):
        response = client.post("/api/cars", json={**base, "vin": bad_vin}, headers=auth_headers)
        assert response.status_code == 422, f"{bad_vin}: {response.text}"


def test_car_accepts_a_vin_whose_check_digit_would_fail(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(vin=GOLF_VIN)
    assert car["vin"][8] == "Z"
    assert car["vin"] == GOLF_VIN
