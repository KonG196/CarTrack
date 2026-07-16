"""Changing a password and an email: the two things that can lose an account."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import User
from app.services import verification
from tests.conftest import DEFAULT_EMAIL, DEFAULT_PASSWORD


def test_password_changes_and_the_old_one_stops_working(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.post(
        "/api/auth/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "new-secret-1"},
        headers=auth_headers,
    )
    assert response.status_code == 204, response.text

    old = client.post(
        "/api/auth/token",
        data={"username": DEFAULT_EMAIL, "password": DEFAULT_PASSWORD},
    )
    assert old.status_code == 401
    new = client.post(
        "/api/auth/token",
        data={"username": DEFAULT_EMAIL, "password": "new-secret-1"},
    )
    assert new.status_code == 200


def test_a_wrong_current_password_changes_nothing(
    client: TestClient, auth_headers: dict
) -> None:
    """Being logged in is not proof of being the owner: a session left open on a
    borrowed laptop is enough to be logged in."""
    response = client.post(
        "/api/auth/password",
        json={"current_password": "not-it", "new_password": "new-secret-1"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    still_works = client.post(
        "/api/auth/token",
        data={"username": DEFAULT_EMAIL, "password": DEFAULT_PASSWORD},
    )
    assert still_works.status_code == 200


def test_password_change_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/api/auth/password", json={"current_password": "x", "new_password": "yyyyyy"}
    )
    assert response.status_code == 401


def test_a_short_new_password_is_refused(client: TestClient, auth_headers: dict) -> None:
    response = client.post(
        "/api/auth/password",
        json={"current_password": "x", "new_password": "12345"},
        headers=auth_headers,
    )
    assert response.status_code == 422


# Email change


@pytest.fixture()
def mail_on(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Mail is off in tests by default (conftest), and the flow needs it on.

    The letter is captured rather than sent: a real send here is what once put
    bounce messages in the owner's inbox.
    """
    sent: list[tuple[str, str]] = []

    def fake_send(to: str, code: str) -> bool:
        sent.append((to, code))
        return True

    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(verification, "send_email_change", fake_send)
    return sent


def test_the_code_goes_to_the_new_address_and_nothing_moves_yet(
    client: TestClient,
    auth_headers: dict,
    db_session_factory: sessionmaker,
    mail_on: list,
) -> None:
    """The address is parked, not written. Login is gated on a verified address,
    so an unconfirmed one in `email` would lock the user out over a typo."""
    response = client.post(
        "/api/auth/email",
        json={"new_email": "moved@example.com", "password": DEFAULT_PASSWORD},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["pending_email"] == "moved@example.com"
    assert mail_on and mail_on[0][0] == "moved@example.com"

    with db_session_factory() as db:
        user = db.execute(select(User)).scalar_one()
        assert user.email == DEFAULT_EMAIL  # unchanged
        assert user.pending_email == "moved@example.com"

    # The old address still logs in while the code is in flight.
    assert (
        client.post(
            "/api/auth/token",
            data={"username": DEFAULT_EMAIL, "password": DEFAULT_PASSWORD},
        ).status_code
        == 200
    )


def test_the_code_completes_the_move(
    client: TestClient, auth_headers: dict, mail_on: list
) -> None:
    client.post(
        "/api/auth/email",
        json={"new_email": "moved@example.com", "password": DEFAULT_PASSWORD},
        headers=auth_headers,
    )
    code = mail_on[0][1]

    response = client.post("/api/auth/email/confirm", json={"code": code}, headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == "moved@example.com"
    assert body["pending_email"] is None

    assert (
        client.post(
            "/api/auth/token",
            data={"username": "moved@example.com", "password": DEFAULT_PASSWORD},
        ).status_code
        == 200
    )


def test_a_wrong_code_moves_nothing(
    client: TestClient, auth_headers: dict, mail_on: list
) -> None:
    client.post(
        "/api/auth/email",
        json={"new_email": "moved@example.com", "password": DEFAULT_PASSWORD},
        headers=auth_headers,
    )
    response = client.post("/api/auth/email/confirm", json={"code": "000000"}, headers=auth_headers)
    assert response.status_code == 400
    assert client.get("/api/auth/me", headers=auth_headers).json()["email"] == DEFAULT_EMAIL


def test_the_wrong_password_cannot_start_a_move(
    client: TestClient, auth_headers: dict, mail_on: list
) -> None:
    response = client.post(
        "/api/auth/email",
        json={"new_email": "moved@example.com", "password": "not-it"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert mail_on == []


def test_an_address_someone_else_holds_is_refused(
    client: TestClient, auth_headers: dict, mail_on: list
) -> None:
    client.post(
        "/api/auth/register", json={"email": "taken@example.com", "password": "secret-123"}
    )
    response = client.post(
        "/api/auth/email",
        json={"new_email": "taken@example.com", "password": DEFAULT_PASSWORD},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert mail_on == []


def test_email_change_is_refused_when_the_server_cannot_mail(
    client: TestClient, auth_headers: dict
) -> None:
    """Without mail the code cannot reach the new address, so the move could
    never be finished — better a plain 503 than a pending change that hangs."""
    response = client.post(
        "/api/auth/email",
        json={"new_email": "moved@example.com", "password": DEFAULT_PASSWORD},
        headers=auth_headers,
    )
    assert response.status_code == 503
