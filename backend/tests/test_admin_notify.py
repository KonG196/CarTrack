"""The owner's "new activity" alerts: one mail per moment, never a repeat.

Each of the four events (signup / first car / first verify / first OCR) must
flip its own `admin_notified_*` flag, address the mail to settings.ADMIN_EMAIL,
and — the whole point of the flags — stay silent on every later trigger.
"""

from __future__ import annotations

from typing import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import User
from app.services import admin_notify, verification


@pytest.fixture
def sent_admin(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Capture every admin mail admin_notify tries to send.

    admin_notify imports send_mail by name, so the patch lands on its module.
    ADMIN_EMAIL is pinned so the recipient assertion is independent of env.
    """
    sent: list[dict] = []

    def fake_send_mail(to, subject, body, html=None, attachments=None):
        sent.append(
            {
                "to": to,
                "subject": subject,
                "body": body,
                "html": html or "",
                "attachments": attachments or [],
            }
        )
        return True

    monkeypatch.setattr(admin_notify, "send_mail", fake_send_mail)
    monkeypatch.setattr(settings, "ADMIN_EMAIL", "owner@example.com")
    return sent


def _user(session_factory: sessionmaker, **overrides) -> User:
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
        # A second call is a no-op: no new mail, flag already latched.
        admin_notify.notify_new_signup(db, user)

    assert len(sent_admin) == 1
    assert sent_admin[0]["to"] == "owner@example.com"
    assert "u@example.com" in sent_admin[0]["body"]
    assert "Maks" in sent_admin[0]["body"]


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
    body = sent_admin[0]["body"]
    # No display name → the raw address stands in for the person.
    assert "carowner@example.com" in body
    # Every filled-in fact makes it into the spec-sheet note.
    assert "Mitsubishi" in body and "L200" in body and "2008" in body
    assert "II" in body and "2.5 DID" in body and "diesel" in body
    assert "258 000 км" in body  # odometer, thin-space grouped
    assert "JMBLYV98H8J000123" in body and "AA1234BB" in body


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


def test_first_ocr_names_the_kind(
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
    body = sent_admin[0]["body"]
    assert "чек" in body
    # Recognised fields land in the note; empty ones are dropped.
    assert "42.5 л" in body and "2473" in body and "ОККО" in body
    assert "Порожнє" not in body
    # The original photo rides along as an attachment.
    assert sent_admin[0]["attachments"] == [image]


def test_no_admin_email_sends_nothing(
    monkeypatch: pytest.MonkeyPatch, db_session_factory: sessionmaker
) -> None:
    """An empty ADMIN_EMAIL disables the whole feature — flag still latches so a
    later config change does not retroactively fire an alert for old activity."""
    sent: list = []
    monkeypatch.setattr(admin_notify, "send_mail", lambda *a, **k: sent.append(a))
    monkeypatch.setattr(settings, "ADMIN_EMAIL", "")

    user = _user(db_session_factory)
    with db_session_factory() as db:
        user = db.merge(user)
        admin_notify.notify_new_signup(db, user)
        assert user.admin_notified_signup is True
    assert sent == []


def test_signup_survives_send_failure(
    monkeypatch: pytest.MonkeyPatch, db_session_factory: sessionmaker
) -> None:
    """A throwing mailer must not bubble out of the notify helper — the flag is
    committed first, so the failed alert is simply skipped, never retried."""
    monkeypatch.setattr(settings, "ADMIN_EMAIL", "owner@example.com")

    def boom(*a, **k):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(admin_notify, "send_mail", boom)

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
    'verified' alert reaches the owner."""
    sent: list[dict] = []
    monkeypatch.setattr(
        admin_notify,
        "send_mail",
        lambda to, s, b, html=None, attachments=None: sent.append({"to": to, "subject": s}) or True,
    )
    monkeypatch.setattr(settings, "ADMIN_EMAIL", "owner@example.com")
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
    signup_alerts = [m for m in sent if "користувач" in m["subject"]]
    assert len(signup_alerts) == 1  # signup alert fired on register

    ok = verification.confirm_verification(
        _session_db(db_session_factory), "verifyme@example.com", codes[-1]
    )
    assert ok is True
    verify_alerts = [m for m in sent if "пошта" in m["subject"]]
    assert len(verify_alerts) == 1
    assert verify_alerts[0]["to"] == "owner@example.com"


def _session_db(session_factory: sessionmaker):
    """confirm_verification wants a live Session; hand it a fresh one."""
    return session_factory()
