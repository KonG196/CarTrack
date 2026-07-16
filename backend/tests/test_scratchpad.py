"""Driver scratchpad: the car field over the API and the bot's /note routing."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.bot import service
from app.models import Car, User


def test_scratchpad_round_trips_over_the_api(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    assert car["scratchpad"] is None

    patched = client.patch(
        f"/api/cars/{car['id']}",
        json={"scratchpad": "ворота двір — код 1234"},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["scratchpad"] == "ворота двір — код 1234"

    fetched = client.get(f"/api/cars/{car['id']}", headers=auth_headers)
    assert fetched.json()["scratchpad"] == "ворота двір — код 1234"

    cleared = client.patch(
        f"/api/cars/{car['id']}", json={"scratchpad": None}, headers=auth_headers
    )
    assert cleared.json()["scratchpad"] is None


def _owner_with_cars(db: Session, count: int, email: str = "n@example.com") -> User:
    user = User(email=email, hashed_password="x", telegram_chat_id=email)
    db.add(user)
    db.flush()
    for i in range(count):
        db.add(
            Car(
                user_id=user.id,
                brand="Skoda",
                model=f"Octavia {i}",
                year=2018,
                fuel_type="petrol",
                current_odometer=1000,
            )
        )
    db.commit()
    return user


def test_note_writes_to_the_single_owned_car(
    db_session_factory: sessionmaker,
) -> None:
    with db_session_factory() as db:
        user = _owner_with_cars(db, 1)
        car = service.set_scratchpad(db, user, "СТО 067 000 00 00")
        assert car is not None
        assert car.scratchpad == "СТО 067 000 00 00"
        pads = service.get_scratchpads(db, user)
        assert [(c.model, note) for c, note in pads] == [("Octavia 0", "СТО 067 000 00 00")]


def test_note_defers_when_no_single_owned_car(
    db_session_factory: sessionmaker,
) -> None:
    with db_session_factory() as db:
        none_owner = _owner_with_cars(db, 0, email="none@example.com")
        assert service.set_scratchpad(db, none_owner, "x") is None
    with db_session_factory() as db:
        multi_owner = _owner_with_cars(db, 2, email="multi@example.com")
        assert service.set_scratchpad(db, multi_owner, "x") is None
