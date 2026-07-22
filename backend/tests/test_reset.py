"""Password reset via Telegram: no-enumeration 202, code lifecycle, single use."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import User
from app.services import reset as reset_service

EMAIL = "reset@example.com"
OLD_PASSWORD = "secret123"
NEW_PASSWORD = "newsecret123"


@pytest.fixture()
def sent_codes(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    sent: list[tuple[str, str]] = []

    async def fake_send(chat_id: str, code: str) -> None:
        sent.append((chat_id, code))

    monkeypatch.setattr(reset_service, "send_reset_code", fake_send)
    return sent


def _link_telegram(db_session_factory: sessionmaker, email: str) -> None:
    with db_session_factory() as db:
        user = db.execute(select(User).where(User.email == email)).scalar_one()
        user.telegram_chat_id = "42"
        db.commit()


def _get_user(db_session_factory: sessionmaker, email: str) -> User:
    with db_session_factory() as db:
        return db.execute(select(User).where(User.email == email)).scalar_one()


def test_reset_happy_path(
    client: TestClient, make_user, db_session_factory: sessionmaker, sent_codes
) -> None:
    make_user(email=EMAIL, password=OLD_PASSWORD)
    _link_telegram(db_session_factory, EMAIL)

    response = client.post("/api/auth/reset/request", json={"email": EMAIL})
    assert response.status_code == 202, response.text
    assert response.json()["detail"] == (
        "If the account exists, we've sent a code."
    )
    assert len(sent_codes) == 1
    chat_id, code = sent_codes[0]
    assert chat_id == "42"
    assert len(code) == 6 and code.isdigit()

    confirm = client.post(
        "/api/auth/reset/confirm",
        json={"email": EMAIL, "code": code, "new_password": NEW_PASSWORD},
    )
    assert confirm.status_code == 200, confirm.text

    # new password logs in, the old one no longer does
    assert (
        client.post(
            "/api/auth/token", data={"username": EMAIL, "password": NEW_PASSWORD}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/auth/token", data={"username": EMAIL, "password": OLD_PASSWORD}
        ).status_code
        == 401
    )


def test_reset_confirm_wrong_code_400(
    client: TestClient, make_user, db_session_factory: sessionmaker, sent_codes
) -> None:
    make_user(email=EMAIL, password=OLD_PASSWORD)
    _link_telegram(db_session_factory, EMAIL)
    client.post("/api/auth/reset/request", json={"email": EMAIL})
    _, code = sent_codes[0]
    wrong = "000000" if code != "000000" else "111111"

    response = client.post(
        "/api/auth/reset/confirm",
        json={"email": EMAIL, "code": wrong, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired code"


def test_reset_confirm_expired_code_400(
    client: TestClient, make_user, db_session_factory: sessionmaker, sent_codes
) -> None:
    make_user(email=EMAIL, password=OLD_PASSWORD)
    _link_telegram(db_session_factory, EMAIL)
    client.post("/api/auth/reset/request", json={"email": EMAIL})
    _, code = sent_codes[0]

    with db_session_factory() as db:
        user = db.execute(select(User).where(User.email == EMAIL)).scalar_one()
        user.reset_code_expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
            minutes=1
        )
        db.commit()

    response = client.post(
        "/api/auth/reset/confirm",
        json={"email": EMAIL, "code": code, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired code"


def test_reset_request_without_telegram_is_202_but_stores_nothing(
    client: TestClient, make_user, db_session_factory: sessionmaker, sent_codes
) -> None:
    make_user(email=EMAIL, password=OLD_PASSWORD)  # no telegram_chat_id

    response = client.post("/api/auth/reset/request", json={"email": EMAIL})
    assert response.status_code == 202
    assert sent_codes == []
    user = _get_user(db_session_factory, EMAIL)
    assert user.reset_code_hash is None
    assert user.reset_code_expires_at is None


def test_reset_request_unknown_email_is_202(client: TestClient, sent_codes) -> None:
    response = client.post(
        "/api/auth/reset/request", json={"email": "ghost@example.com"}
    )
    assert response.status_code == 202
    assert sent_codes == []


def test_reset_code_is_single_use(
    client: TestClient, make_user, db_session_factory: sessionmaker, sent_codes
) -> None:
    make_user(email=EMAIL, password=OLD_PASSWORD)
    _link_telegram(db_session_factory, EMAIL)
    client.post("/api/auth/reset/request", json={"email": EMAIL})
    _, code = sent_codes[0]

    first = client.post(
        "/api/auth/reset/confirm",
        json={"email": EMAIL, "code": code, "new_password": NEW_PASSWORD},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/auth/reset/confirm",
        json={"email": EMAIL, "code": code, "new_password": "anothersecret1"},
    )
    assert second.status_code == 400  # the code was cleared on success


def test_reset_confirm_jwt_as_code_is_uniform_400(
    client: TestClient, make_user, db_session_factory: sessionmaker, sent_codes
) -> None:
    # A pasted access token (or any wrong-length garbage) must get the same
    # 400 as a wrong 6-digit code — not a 422 that echoes the input back.
    headers = make_user(email=EMAIL, password=OLD_PASSWORD)
    _link_telegram(db_session_factory, EMAIL)
    client.post("/api/auth/reset/request", json={"email": EMAIL})
    access_token = headers["Authorization"].removeprefix("Bearer ")

    response = client.post(
        "/api/auth/reset/confirm",
        json={"email": EMAIL, "code": access_token, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired code"


def test_reset_confirm_short_password_422(client: TestClient) -> None:
    response = client.post(
        "/api/auth/reset/confirm",
        json={"email": EMAIL, "code": "123456", "new_password": "short"},
    )
    assert response.status_code == 422


def test_reset_without_telegram_goes_by_email(client, monkeypatch) -> None:
    """No bot linked is no longer a dead end: the letter is the way back."""
    from app.services import reset as reset_service

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(reset_service, "mail_enabled", lambda: True)
    monkeypatch.setattr(
        reset_service,
        "send_reset_code_mail",
        lambda to, code, lang="en": sent.append((to, code)) or True,
    )

    client.post(
        "/api/auth/register", json={"email": "nobot@example.com", "password": "password123"}
    )
    response = client.post("/api/auth/reset/request", json={"email": "nobot@example.com"})
    assert response.status_code == 202
    assert len(sent) == 1

    confirmed = client.post(
        "/api/auth/reset/confirm",
        json={"email": "nobot@example.com", "code": sent[0][1], "new_password": "brandnew123"},
    )
    assert confirmed.status_code == 200
    assert (
        client.post(
            "/api/auth/token",
            data={"username": "nobot@example.com", "password": "brandnew123"},
        ).status_code
        == 200
    )


def test_channel_email_is_honoured_even_with_telegram_linked(
    client, monkeypatch, db_session_factory
) -> None:
    """Picking email must not be overridden by a linked bot."""
    from app.services import reset as reset_service

    mailed: list[tuple[str, str]] = []
    telegrammed: list[str] = []
    monkeypatch.setattr(reset_service, "mail_enabled", lambda: True)
    monkeypatch.setattr(
        reset_service, "send_reset_code_mail", lambda to, code, lang="en": mailed.append((to, code)) or True
    )

    async def fake_telegram(chat_id, code):
        telegrammed.append(chat_id)

    monkeypatch.setattr(reset_service, "send_reset_code", fake_telegram)

    client.post(
        "/api/auth/register", json={"email": "both@example.com", "password": "password123"}
    )
    _link_telegram(db_session_factory, "both@example.com")

    client.post(
        "/api/auth/reset/request", json={"email": "both@example.com", "channel": "email"}
    )
    assert len(mailed) == 1
    assert telegrammed == []


def test_channel_telegram_falls_back_to_mail_when_not_linked(client, monkeypatch) -> None:
    """Asking for the bot without one linked still gets the user back in."""
    from app.services import reset as reset_service

    mailed: list[tuple[str, str]] = []
    monkeypatch.setattr(reset_service, "mail_enabled", lambda: True)
    monkeypatch.setattr(
        reset_service, "send_reset_code_mail", lambda to, code, lang="en": mailed.append((to, code)) or True
    )

    client.post(
        "/api/auth/register", json={"email": "nobot2@example.com", "password": "password123"}
    )
    response = client.post(
        "/api/auth/reset/request", json={"email": "nobot2@example.com", "channel": "telegram"}
    )
    assert response.status_code == 202
    assert len(mailed) == 1
