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


def test_password_change_revokes_other_tokens_but_keeps_this_session(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/api/auth/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "brand-new-1"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    # The old token (any other session) is now dead...
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 401
    # ...but the fresh pair returned to the caller keeps THIS session alive.
    fresh = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=fresh).status_code == 200


def test_refresh_issues_a_new_access_token(
    client: TestClient, auth_headers: dict[str, str]  # noqa: ARG001 — registers the user
) -> None:
    login = client.post(
        "/api/auth/token", data={"username": DEFAULT_EMAIL, "password": DEFAULT_PASSWORD}
    )
    assert login.status_code == 200, login.text
    refresh = login.json()["refresh_token"]
    assert refresh

    r = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200, r.text
    new_access = r.json()["access_token"]
    assert client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {new_access}"}
    ).status_code == 200


def test_access_token_is_rejected_at_refresh(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    access = auth_headers["Authorization"].split()[1]
    # An access token has no refresh purpose -> cannot be spent for a new one.
    assert client.post("/api/auth/refresh", json={"refresh_token": access}).status_code == 401


def test_refresh_dies_after_password_change(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    login = client.post(
        "/api/auth/token", data={"username": DEFAULT_EMAIL, "password": DEFAULT_PASSWORD}
    )
    refresh = login.json()["refresh_token"]
    client.post(
        "/api/auth/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "brand-new-1"},
        headers=auth_headers,
    )
    # token_version moved on, so the old refresh token no longer refreshes.
    assert client.post("/api/auth/refresh", json={"refresh_token": refresh}).status_code == 401


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
