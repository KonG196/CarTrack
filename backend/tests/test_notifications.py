"""In-app notification centre: which signals become notifications."""

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models import Car, CarDocument, ServiceInterval, TireSet, User
from app.services.notifications import build_notifications

TODAY = dt.date(2026, 7, 21)


def _owner(db: Session, email: str = "notify@example.com", **car_kwargs) -> tuple[User, Car]:
    user = User(email=email, hashed_password="x")
    db.add(user)
    db.flush()
    car = Car(
        user_id=user.id,
        brand="VW",
        model="Golf",
        year=2016,
        fuel_type="diesel",
        current_odometer=50000,
        **car_kwargs,
    )
    db.add(car)
    db.flush()
    return user, car


def _kinds(notes: list[dict]) -> set[str]:
    return {note["kind"] for note in notes}


def test_overdue_interval_becomes_a_crit_notification(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        user, car = _owner(db)
        # due at 49 000 km, car at 50 000 -> overdue by 1 000
        db.add(ServiceInterval(car_id=car.id, title="Олива", interval_km=10000, last_odometer=39000))
        db.commit()
        notes = build_notifications(db, user, today=TODAY)
        interval_notes = [n for n in notes if n["kind"] == "interval"]
        assert len(interval_notes) == 1
        assert interval_notes[0]["severity"] == "crit"
        assert "прострочено" in interval_notes[0]["body"]
        assert interval_notes[0]["action"] == "/intervals"


def test_insurance_expiry_within_a_week_is_crit(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        user, _car = _owner(db, insurance_until=TODAY + dt.timedelta(days=5))
        db.commit()
        notes = build_notifications(db, user, today=TODAY)
        insurance = [n for n in notes if n["kind"] == "insurance"]
        assert len(insurance) == 1
        assert insurance[0]["severity"] == "crit"


def test_far_insurance_and_ancient_lapse_are_silent(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        user, _car = _owner(db, email="far@example.com", insurance_until=TODAY + dt.timedelta(days=200))
        db.commit()
        assert "insurance" not in _kinds(build_notifications(db, user, today=TODAY))
    with db_session_factory() as db:
        user, _car = _owner(db, email="ancient@example.com", insurance_until=TODAY - dt.timedelta(days=200))
        db.commit()
        assert "insurance" not in _kinds(build_notifications(db, user, today=TODAY))


def _document(car_id: int, kind: str, expires_at: dt.date) -> CarDocument:
    return CarDocument(
        car_id=car_id,
        kind=kind,
        title=kind,
        filename="scan.pdf",
        content_type="application/pdf",
        size=1,
        expires_at=expires_at,
    )


def test_inspection_document_does_not_silence_insurance_nudge(
    db_session_factory: sessionmaker,
) -> None:
    # A техогляд document books a "(документ)" interval too — it must NOT suppress
    # the unrelated ОСЦПВ deadline nudge.
    with db_session_factory() as db:
        user, car = _owner(db, insurance_until=TODAY + dt.timedelta(days=5))
        db.add(_document(car.id, "inspection", TODAY + dt.timedelta(days=100)))
        db.commit()
        assert "insurance" in _kinds(build_notifications(db, user, today=TODAY))


def test_insurance_document_silences_the_date_field_nudge(
    db_session_factory: sessionmaker,
) -> None:
    # An uploaded insurance policy already books its own deadline reminder, so the
    # insurance_until field nudge stands down to avoid double-nudging.
    with db_session_factory() as db:
        user, car = _owner(db, insurance_until=TODAY + dt.timedelta(days=5))
        db.add(_document(car.id, "insurance", TODAY + dt.timedelta(days=5)))
        db.commit()
        assert "insurance" not in _kinds(build_notifications(db, user, today=TODAY))


def test_old_mounted_tyre_set_notifies(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        user, car = _owner(db)
        db.add(TireSet(car_id=car.id, name="Літо", season="summer", is_installed=True, dot_year=2017))
        db.commit()
        notes = build_notifications(db, user, today=TODAY)
        age = [n for n in notes if n["kind"] == "tire_age"]
        assert len(age) == 1
        assert age[0]["severity"] == "crit"  # 9 years old


def test_healthy_car_has_no_notifications(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        user, _car = _owner(db)
        db.commit()
        assert build_notifications(db, user, today=TODAY) == []


def test_endpoint_returns_the_list(client: TestClient, auth_headers: dict, make_car) -> None:
    car = make_car(current_odometer=50000)
    client.post(
        f"/api/cars/{car['id']}/intervals",
        json={"title": "Олива", "interval_km": 10000, "last_odometer": 39000},
        headers=auth_headers,
    )
    response = client.get("/api/notifications", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] >= 1
    assert any(note["kind"] == "interval" for note in body["items"])
