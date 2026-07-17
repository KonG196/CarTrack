"""Session revocation, reset-code lockout, and single-use invites."""

import datetime as dt
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.auth import hash_password
from app.models import User
from app.services.reset import confirm_reset
from tests.conftest import DEFAULT_EMAIL, DEFAULT_PASSWORD


def test_password_change_revokes_existing_tokens(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/api/auth/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "brand-new-1"},
        headers=auth_headers,
    )
    assert resp.status_code == 204, resp.text
    # The token that was valid a moment ago now carries a stale version.
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 401
    # A fresh login works and mints a token with the new version.
    again = client.post(
        "/api/auth/token", data={"username": DEFAULT_EMAIL, "password": "brand-new-1"}
    )
    assert again.status_code == 200, again.text
    new_headers = {"Authorization": f"Bearer {again.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=new_headers).status_code == 200


def test_reset_code_burns_after_five_wrong_attempts(
    client: TestClient,  # noqa: ARG001 — creates the app/db and the seeded user
    auth_headers: dict[str, str],  # noqa: ARG001 — registers DEFAULT_EMAIL
    db_session_factory: sessionmaker,
) -> None:
    with db_session_factory() as db:
        user = db.execute(select(User).where(User.email == DEFAULT_EMAIL)).scalar_one()
        user.reset_code_hash = hash_password("123456")
        user.reset_code_expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10)
        user.reset_code_attempts = 0
        db.commit()

    # Five wrong guesses (service level, so no IP limiter in the way).
    for _ in range(5):
        with db_session_factory() as db:
            assert confirm_reset(db, DEFAULT_EMAIL, "000000", "whatever-1") is False
    # The code is now burned: even the correct one no longer works.
    with db_session_factory() as db:
        assert confirm_reset(db, DEFAULT_EMAIL, "123456", "whatever-1") is False
        user = db.execute(select(User).where(User.email == DEFAULT_EMAIL)).scalar_one()
        assert user.reset_code_hash is None


def test_invite_is_single_use(
    client: TestClient,
    auth_headers: dict[str, str],
    make_car: Callable[..., dict],
    make_user: Callable[..., dict[str, str]],
) -> None:
    car = make_car()
    token = client.post(
        f"/api/cars/{car['id']}/invites", json={"role": "editor"}, headers=auth_headers
    ).json()["token"]

    friend = make_user(email="friend@example.com")
    assert client.post(f"/api/invites/{token}/accept", headers=friend).status_code == 201
    # The link is spent — a second person cannot ride it in.
    stranger = make_user(email="stranger@example.com")
    assert client.post(f"/api/invites/{token}/accept", headers=stranger).status_code == 404
