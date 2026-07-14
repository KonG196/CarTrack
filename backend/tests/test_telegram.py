"""Telegram linking: link-code JWT lifecycle + the /api/telegram endpoints."""

import datetime as dt

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.bot import service
from app.config import settings
from app.routers.telegram import (
    LINK_CODE_PURPOSE,
    InvalidLinkCodeError,
    decode_link_code,
)

CHAT_ID = "123456789"


def _make_code(
    user_id: int, purpose: str = LINK_CODE_PURPOSE, expires_minutes: int = 15
) -> str:
    expire = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=expires_minutes)
    return jwt.encode(
        {"sub": str(user_id), "purpose": purpose, "exp": expire},
        settings.SECRET_KEY,
        algorithm="HS256",
    )


def test_link_code_roundtrip(
    client: TestClient, auth_headers: dict, db_session_factory: sessionmaker
) -> None:
    response = client.post("/api/telegram/link-code", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["expires_in_minutes"] == settings.LINK_CODE_EXPIRE_MINUTES
    # deep link only exists when a bot username is configured
    if settings.TELEGRAM_BOT_USERNAME:
        assert body["deep_link"] == (
            f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={body['code']}"
        )
    else:
        assert body["deep_link"] is None

    user_id = decode_link_code(body["code"])

    with db_session_factory() as db:
        user = service.link_user_by_code(db, body["code"], chat_id=CHAT_ID)
        assert user.id == user_id
        assert user.telegram_chat_id == CHAT_ID

    status = client.get("/api/telegram/status", headers=auth_headers)
    assert status.status_code == 200
    assert status.json() == {"linked": True}

    deleted = client.delete("/api/telegram/link", headers=auth_headers)
    assert deleted.status_code == 204

    status = client.get("/api/telegram/status", headers=auth_headers)
    assert status.json() == {"linked": False}


def test_expired_link_code_rejected() -> None:
    code = _make_code(1, expires_minutes=-1)
    with pytest.raises(InvalidLinkCodeError):
        decode_link_code(code)


def test_garbage_link_code_rejected() -> None:
    with pytest.raises(InvalidLinkCodeError):
        decode_link_code("definitely-not-a-jwt")


def test_wrong_purpose_link_code_rejected() -> None:
    code = _make_code(1, purpose="password-reset")
    with pytest.raises(InvalidLinkCodeError):
        decode_link_code(code)


def test_tampered_signature_link_code_rejected() -> None:
    code = _make_code(1)
    header, payload, signature = code.split(".")
    forged_signature = ("A" if not signature.startswith("A") else "B") + signature[1:]
    with pytest.raises(InvalidLinkCodeError):
        decode_link_code(f"{header}.{payload}.{forged_signature}")


def test_link_code_signed_with_wrong_key_rejected() -> None:
    expire = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=15)
    code = jwt.encode(
        {"sub": "1", "purpose": LINK_CODE_PURPOSE, "exp": expire},
        "not-the-real-secret-key-of-at-least-32-bytes",
        algorithm="HS256",
    )
    with pytest.raises(InvalidLinkCodeError):
        decode_link_code(code)


def test_link_code_cannot_be_used_as_access_token(
    client: TestClient, auth_headers: dict
) -> None:
    # the reverse of "access token as link code": a tg-link JWT pasted as a
    # Bearer token must not authenticate API requests
    code = client.post("/api/telegram/link-code", headers=auth_headers).json()["code"]
    response = client.get("/api/cars", headers={"Authorization": f"Bearer {code}"})
    assert response.status_code == 401


def test_unlink_is_idempotent(
    client: TestClient, auth_headers: dict, db_session_factory: sessionmaker
) -> None:
    code = client.post("/api/telegram/link-code", headers=auth_headers).json()["code"]
    with db_session_factory() as db:
        service.link_user_by_code(db, code, chat_id=CHAT_ID)
        assert service.unlink_chat(db, CHAT_ID) is True
        # already unlinked: reports False, does not raise
        assert service.unlink_chat(db, CHAT_ID) is False

    # the HTTP unlink is idempotent too: repeated DELETEs keep returning 204
    assert client.delete("/api/telegram/link", headers=auth_headers).status_code == 204
    assert client.delete("/api/telegram/link", headers=auth_headers).status_code == 204
    assert client.get("/api/telegram/status", headers=auth_headers).json() == {
        "linked": False
    }


def test_wrong_purpose_code_does_not_link(
    client: TestClient, auth_headers: dict, db_session_factory: sessionmaker
) -> None:
    # a valid *access* token has no purpose claim and must be rejected too
    access_token = auth_headers["Authorization"].removeprefix("Bearer ")
    with db_session_factory() as db:
        with pytest.raises(InvalidLinkCodeError):
            service.link_user_by_code(db, access_token, chat_id=CHAT_ID)

    status = client.get("/api/telegram/status", headers=auth_headers)
    assert status.json() == {"linked": False}


def test_relinking_chat_moves_it_to_the_new_user(
    client: TestClient, make_user, db_session_factory: sessionmaker
) -> None:
    first_headers = make_user()
    second_headers = make_user(email="second@example.com")

    first_code = client.post("/api/telegram/link-code", headers=first_headers).json()[
        "code"
    ]
    second_code = client.post("/api/telegram/link-code", headers=second_headers).json()[
        "code"
    ]

    with db_session_factory() as db:
        first_user = service.link_user_by_code(db, first_code, chat_id=CHAT_ID)
        assert first_user.telegram_chat_id == CHAT_ID

        second_user = service.link_user_by_code(db, second_code, chat_id=CHAT_ID)
        assert second_user.telegram_chat_id == CHAT_ID
        assert second_user.id != first_user.id

    assert client.get("/api/telegram/status", headers=first_headers).json() == {
        "linked": False
    }
    assert client.get("/api/telegram/status", headers=second_headers).json() == {
        "linked": True
    }


def test_telegram_endpoints_require_auth(client: TestClient) -> None:
    assert client.post("/api/telegram/link-code").status_code == 401
    assert client.get("/api/telegram/status").status_code == 401
    assert client.delete("/api/telegram/link").status_code == 401
