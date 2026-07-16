"""Tire axle-rotation: the 10k cadence, the rotate endpoint, and the nudge."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.bot import service
from app.models import Car, TireSet, User
from app.services.tires import due_rotation_km


def _create_tires(client: TestClient, headers: dict, car_id: int, **overrides) -> dict:
    payload = {"name": "Літо Michelin", "season": "summer"}
    payload.update(overrides)
    response = client.post(f"/api/cars/{car_id}/tires", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _set_odometer(db_session_factory: sessionmaker, car_id: int, odometer: int) -> None:
    with db_session_factory() as db:
        car = db.execute(select(Car).where(Car.id == car_id)).scalar_one()
        car.current_odometer = odometer
        db.commit()


def test_due_rotation_km_fires_once_per_10k() -> None:
    assert due_rotation_km(None, None) is None
    assert due_rotation_km(9_999, None) is None
    assert due_rotation_km(10_000, None) == 10_000
    assert due_rotation_km(10_500, None) == 10_000
    assert due_rotation_km(10_500, 10_000) is None  # already nudged at 10k
    assert due_rotation_km(20_000, 10_000) == 20_000
    assert due_rotation_km(20_000, 20_000) is None


def test_install_stamps_rotation_and_rotate_resets(
    client: TestClient, auth_headers: dict, make_car, db_session_factory: sessionmaker
) -> None:
    car = make_car(current_odometer=5000)
    tires = _create_tires(client, auth_headers, car["id"])
    client.post(f"/api/tires/{tires['id']}/install", headers=auth_headers)

    _set_odometer(db_session_factory, car["id"], 15000)  # +10 000 km
    listed = client.get(f"/api/cars/{car['id']}/tires", headers=auth_headers).json()
    assert listed[0]["km_since_rotation"] == 10000

    rotated = client.post(f"/api/tires/{tires['id']}/rotate", headers=auth_headers)
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["km_since_rotation"] == 0


def test_rotate_shelf_set_is_conflict(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    shelf = _create_tires(client, auth_headers, car["id"])  # never installed
    response = client.post(f"/api/tires/{shelf['id']}/rotate", headers=auth_headers)
    assert response.status_code == 409


def test_rotation_reminder_fires_dedups_and_advances(
    db_session_factory: sessionmaker,
) -> None:
    with db_session_factory() as db:
        user = User(email="r@example.com", hashed_password="x", telegram_chat_id="5")
        db.add(user)
        db.flush()
        car = Car(
            user_id=user.id,
            brand="Skoda",
            model="Octavia",
            year=2018,
            fuel_type="petrol",
            current_odometer=10000,
        )
        db.add(car)
        db.flush()
        tire_set = TireSet(
            car_id=car.id,
            name="s",
            season="summer",
            is_installed=True,
            odometer_at_install=0,
            odometer_at_rotation=0,
        )
        db.add(tire_set)
        db.commit()

        targets = service.rotation_reminder_targets(db)
        assert len(targets) == 1
        _user, reminder = targets[0]
        assert reminder.due_km == 10000
        assert reminder.km_since_rotation == 10000

        service.stamp_rotation(db, reminder.tire_set, reminder.due_km)
        assert service.rotation_reminder_targets(db) == []

        # Another 10k without rotating -> nudged again at the 20k mark.
        car.current_odometer = 20000
        db.commit()
        again = service.rotation_reminder_targets(db)
        assert len(again) == 1
        assert again[0][1].due_km == 20000


def test_no_rotation_nudge_when_off(db_session_factory) -> None:
    with db_session_factory() as db:
        user = User(
            email="rr@example.com", hashed_password="x",
            telegram_chat_id="6", notify_rotation=False,
        )
        db.add(user)
        db.flush()
        car = Car(user_id=user.id, brand="Skoda", model="Octavia", year=2018,
                  fuel_type="petrol", current_odometer=10000)
        db.add(car)
        db.flush()
        db.add(TireSet(car_id=car.id, name="s", season="summer", is_installed=True,
                       odometer_at_install=0, odometer_at_rotation=0))
        db.commit()
        assert service.rotation_reminder_targets(db) == []


def test_bot_rotate_records_resets_and_is_owner_only(db_session_factory) -> None:
    with db_session_factory() as db:
        owner = User(email="rot@example.com", hashed_password="x", telegram_chat_id="9")
        db.add(owner)
        db.flush()
        car = Car(user_id=owner.id, brand="Skoda", model="Octavia", year=2018,
                  fuel_type="petrol", current_odometer=25000)
        db.add(car)
        db.flush()
        mounted = TireSet(car_id=car.id, name="s", season="summer", is_installed=True,
                          odometer_at_install=0, odometer_at_rotation=0,
                          rotation_reminded_km=20000)
        shelf = TireSet(car_id=car.id, name="shelf", season="winter", is_installed=False)
        stranger = User(email="str@example.com", hashed_password="x", telegram_chat_id="10")
        db.add_all([mounted, shelf, stranger])
        db.commit()

        # A stranger cannot rotate someone else's set; a shelf set cannot rotate.
        assert service.rotate_tire_set(db, stranger, mounted.id) is None
        assert service.rotate_tire_set(db, owner, shelf.id) is None

        # The owner records it: the clock resets and the nudge is gone.
        result = service.rotate_tire_set(db, owner, mounted.id)
        assert result is not None
        assert mounted.odometer_at_rotation == 25000
        assert mounted.rotation_reminded_km is None
        assert mounted.km_since_rotation == 0
        assert service.rotation_reminder_targets(db) == []
