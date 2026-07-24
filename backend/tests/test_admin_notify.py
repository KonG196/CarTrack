"""The owner's "new activity" alerts: one Telegram message per moment, never a
repeat.

Each of the four events (signup / first car / first verify / first OCR) must
flip its own `admin_notified_*` flag, send exactly one message to the admin bot,
and — the whole point of the flags — stay silent on every later trigger.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.services import admin_notify, verification


@pytest.fixture
def sent_admin(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Capture every admin Telegram message admin_notify tries to send.

    admin_notify imports send_admin_message by name, so the patch lands on its
    module. The real sender is bypassed entirely (no config, no network)."""
    sent: list[dict] = []

    def fake_send(text, photo=None):
        sent.append({"text": text, "photo": photo})
        return True

    monkeypatch.setattr(admin_notify, "send_admin_message", fake_send)
    return sent


def _user(session_factory: sessionmaker, **overrides) -> "object":
    from app.models import User

    with session_factory() as db:
        user = User(
            email=overrides.pop("email", "u@example.com"),
            hashed_password="x",
            display_name=overrides.pop("display_name", "Maks"),
            **overrides,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
        return user


def test_signup_notifies_owner_once(
    sent_admin: list[dict], db_session_factory: sessionmaker
) -> None:
    user = _user(db_session_factory)
    with db_session_factory() as db:
        user = db.merge(user)
        admin_notify.notify_new_signup(db, user)
        assert user.admin_notified_signup is True
        # A second call is a no-op: no new message, flag already latched.
        admin_notify.notify_new_signup(db, user)

    assert len(sent_admin) == 1
    assert "u@example.com" in sent_admin[0]["text"]
    assert "Maks" in sent_admin[0]["text"]


def test_first_car_includes_car_line(
    sent_admin: list[dict], db_session_factory: sessionmaker
) -> None:
    from app.models import Car

    user = _user(db_session_factory, email="carowner@example.com", display_name="")
    with db_session_factory() as db:
        user = db.merge(user)
        car = Car(
            user_id=user.id,
            brand="Mitsubishi",
            model="L200",
            year=2008,
            fuel_type="diesel",
            generation="II",
            engine="2.5 DID",
            current_odometer=258000,
            vin="JMBLYV98H8J000123",
            plate="AA1234BB",
        )
        db.add(car)
        db.flush()
        admin_notify.notify_first_car(db, user, car)
        assert user.admin_notified_first_car is True

    assert len(sent_admin) == 1
    text = sent_admin[0]["text"]
    # No display name → the raw address stands in for the person.
    assert "carowner@example.com" in text
    # Every filled-in fact makes it into the spec-sheet note.
    assert "Mitsubishi" in text and "L200" in text and "2008" in text
    assert "II" in text and "2.5 DID" in text and "diesel" in text
    assert "258 000 км" in text  # odometer, thin-space grouped
    assert "JMBLYV98H8J000123" in text and "AA1234BB" in text


def test_first_verified_latches(
    sent_admin: list[dict], db_session_factory: sessionmaker
) -> None:
    user = _user(db_session_factory)
    with db_session_factory() as db:
        user = db.merge(user)
        admin_notify.notify_first_verified(db, user)
        admin_notify.notify_first_verified(db, user)
        assert user.admin_notified_verified is True
    assert len(sent_admin) == 1


def test_first_ocr_names_the_kind_and_attaches_photo(
    sent_admin: list[dict], db_session_factory: sessionmaker
) -> None:
    user = _user(db_session_factory)
    fields = {"Літри": "42.5 л", "Сума": 2473, "АЗС": "ОККО", "Порожнє": None}
    image = ("receipt.jpg", b"\xff\xd8\xfffakejpeg", "image/jpeg")
    with db_session_factory() as db:
        user = db.merge(user)
        admin_notify.notify_first_ocr(db, user, "чек", fields, image)
        admin_notify.notify_first_ocr(db, user, "чек", fields, image)
        assert user.admin_notified_first_ocr is True
    assert len(sent_admin) == 1
    text = sent_admin[0]["text"]
    assert "чек" in text
    # Recognised fields land in the note; empty ones are dropped.
    assert "42.5 л" in text and "2473" in text and "ОККО" in text
    assert "Порожнє" not in text
    # The original photo rides along as the Telegram photo.
    assert sent_admin[0]["photo"] == image


def test_disabled_admin_bot_sends_nothing(
    monkeypatch: pytest.MonkeyPatch, db_session_factory: sessionmaker
) -> None:
    """With the admin bot unconfigured the real sender returns False and nothing
    goes out — but the flag still latches so a later config change does not
    retroactively fire an alert for old activity."""
    from app.config import settings

    # Real sender, but no token/chat → admin_telegram_enabled() is False.
    monkeypatch.setattr(settings, "ADMIN_BOT_TOKEN", "")
    monkeypatch.setattr(settings, "ADMIN_TELEGRAM_CHAT_ID", "")

    user = _user(db_session_factory)
    with db_session_factory() as db:
        user = db.merge(user)
        admin_notify.notify_new_signup(db, user)
        assert user.admin_notified_signup is True  # latched regardless


def test_signup_survives_send_failure(
    monkeypatch: pytest.MonkeyPatch, db_session_factory: sessionmaker
) -> None:
    """A throwing sender must not bubble out of the notify helper — the flag is
    committed first, so the failed alert is simply skipped, never retried."""

    def boom(*a, **k):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(admin_notify, "send_admin_message", boom)

    user = _user(db_session_factory)
    with db_session_factory() as db:
        user = db.merge(user)
        admin_notify.notify_new_signup(db, user)  # must not raise
        db.refresh(user)
        assert user.admin_notified_signup is True


def test_verification_flow_fires_admin_alert(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, db_session_factory: sessionmaker
) -> None:
    """End-to-end: register with mail on, then confirm the code, and exactly one
    'verified' alert reaches the owner (plus the signup alert on register)."""
    sent: list[str] = []
    monkeypatch.setattr(
        admin_notify, "send_admin_message", lambda text, photo=None: sent.append(text) or True
    )
    monkeypatch.setattr(verification, "mail_enabled", lambda: True)

    codes: list[str] = []
    monkeypatch.setattr(
        verification, "send_verification", lambda to, code, lang="en": codes.append(code) or True
    )

    resp = client.post(
        "/api/auth/register",
        json={"email": "verifyme@example.com", "password": "password123"},
    )
    assert resp.status_code == 201
    signup_alerts = [m for m in sent if "Новий користувач" in m]
    assert len(signup_alerts) == 1  # signup alert fired on register

    with db_session_factory() as db:
        ok = verification.confirm_verification(db, "verifyme@example.com", codes[-1])
    assert ok is True
    verify_alerts = [m for m in sent if "Пошту підтверджено" in m]
    assert len(verify_alerts) == 1
