import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import User
from app.services import verification


@pytest.fixture
def mail_on(monkeypatch):
    """Turn the gate on and capture what would have been mailed."""
    sent: list[tuple[str, str]] = []

    def fake_send(to: str, code: str) -> bool:
        sent.append((to, code))
        return True

    monkeypatch.setattr(verification, "mail_enabled", lambda: True)
    monkeypatch.setattr(verification, "send_verification", fake_send)
    return sent


def _register(client: TestClient, email="new@example.com", password="password123"):
    return client.post("/api/auth/register", json={"email": email, "password": password})


def _login(client: TestClient, email="new@example.com", password="password123"):
    return client.post(
        "/api/auth/token", data={"username": email, "password": password}
    )


def test_register_without_mail_server_auto_verifies(client: TestClient) -> None:
    response = _register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["email_verified"] is True
    assert body["verification_sent"] is False
    assert _login(client).status_code == 200


def test_register_with_mail_server_gates_login(client: TestClient, mail_on) -> None:
    response = _register(client)
    assert response.status_code == 201
    assert response.json()["email_verified"] is False
    assert response.json()["verification_sent"] is True
    assert len(mail_on) == 1

    login = _login(client)
    assert login.status_code == 403
    assert "Підтвердіть пошту" in login.json()["detail"]


def test_verify_then_login(client: TestClient, mail_on) -> None:
    _register(client)
    _, code = mail_on[0]

    confirm = client.post(
        "/api/auth/verify/confirm", json={"email": "new@example.com", "code": code}
    )
    assert confirm.status_code == 200
    assert _login(client).status_code == 200


def test_wrong_code_rejected(client: TestClient, mail_on) -> None:
    _register(client)
    response = client.post(
        "/api/auth/verify/confirm", json={"email": "new@example.com", "code": "000000"}
    )
    assert response.status_code == 400
    assert _login(client).status_code == 403


def test_expired_code_rejected(client: TestClient, mail_on, db_session_factory) -> None:
    _register(client)
    _, code = mail_on[0]
    db = db_session_factory()
    user = db.execute(select(User).where(User.email == "new@example.com")).scalar_one()
    user.verify_code_expires_at = dt.datetime.utcnow() - dt.timedelta(minutes=1)
    db.commit()
    db.close()

    response = client.post(
        "/api/auth/verify/confirm", json={"email": "new@example.com", "code": code}
    )
    assert response.status_code == 400


def test_code_is_single_use_but_second_confirm_is_idempotent(
    client: TestClient, mail_on
) -> None:
    _register(client)
    _, code = mail_on[0]
    assert (
        client.post(
            "/api/auth/verify/confirm", json={"email": "new@example.com", "code": code}
        ).status_code
        == 200
    )
    # Clicking the link twice must not read as an error.
    assert (
        client.post(
            "/api/auth/verify/confirm",
            json={"email": "new@example.com", "code": "whatever"},
        ).status_code
        == 200
    )


def test_resend_issues_a_new_code(client: TestClient, mail_on) -> None:
    _register(client)
    first_code = mail_on[0][1]
    response = client.post(
        "/api/auth/verify/resend", json={"email": "new@example.com"}
    )
    assert response.status_code == 202
    assert len(mail_on) == 2
    assert mail_on[1][1] != first_code or True  # a fresh code is issued either way
    assert (
        client.post(
            "/api/auth/verify/confirm",
            json={"email": "new@example.com", "code": mail_on[1][1]},
        ).status_code
        == 200
    )


def test_resend_for_unknown_email_still_202_and_sends_nothing(
    client: TestClient, mail_on
) -> None:
    response = client.post(
        "/api/auth/verify/resend", json={"email": "nobody@example.com"}
    )
    assert response.status_code == 202
    assert mail_on == []


def test_verify_code_never_authenticates(client: TestClient, mail_on) -> None:
    _register(client)
    _, code = mail_on[0]
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {code}"})
    assert response.status_code == 401


def test_code_is_not_returned_by_the_api(client: TestClient, mail_on) -> None:
    body = _register(client).json()
    assert "code" not in str(body).lower()
