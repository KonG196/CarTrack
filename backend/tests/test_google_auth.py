"""Google sign-in endpoint: /auth/google.

The Google token verification itself is not exercised here (it needs Google's
network + keys); we monkeypatch the router's verifier and test the account
logic: create-on-first-login, merge-by-email, and the auto-verify side effect.
"""

import pytest
from fastapi.testclient import TestClient

from app.models import User
from app.routers import auth as auth_router
from app.services.google_auth import (
    GoogleAuthError,
    GoogleAuthUnavailable,
    GoogleIdentity,
)


@pytest.fixture
def fake_google(monkeypatch):
    """Make the endpoint trust a token and return a fixed identity."""

    def _set(email="g@example.com", email_verified=True):
        monkeypatch.setattr(
            auth_router,
            "verify_google_id_token",
            lambda token: GoogleIdentity(email=email, email_verified=email_verified, sub="google-123"),
        )

    return _set


def test_google_login_creates_a_new_verified_account(client: TestClient, fake_google):
    fake_google(email="new.google@example.com")
    r = client.post("/api/auth/google", json={"id_token": "x", "language": "uk", "currency": "EUR"})
    assert r.status_code == 200
    assert "access_token" in r.json()

    # The account exists, is verified, has no password, and is a google account.
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    body = me.json()
    assert body["email"] == "new.google@example.com"
    assert body["email_verified"] is True
    assert body["auth_provider"] == "google"


def test_google_login_merges_and_verifies_an_existing_account(
    client: TestClient, fake_google, db_session_factory
):
    # A password account, still unverified.
    client.post("/api/auth/register", json={"email": "merge@example.com", "password": "password123"})
    # Signing in with Google for the same address logs into it AND verifies it.
    fake_google(email="merge@example.com")
    r = client.post("/api/auth/google", json={"id_token": "x"})
    assert r.status_code == 200

    db = db_session_factory()
    user = db.query(User).filter(User.email == "merge@example.com").one()
    assert user.email_verified is True
    # It stays a password account — the person can still use their password.
    assert user.hashed_password is not None
    db.close()


def test_google_login_rejects_an_unverified_google_email(client: TestClient, fake_google):
    fake_google(email="sketchy@example.com", email_verified=False)
    r = client.post("/api/auth/google", json={"id_token": "x"})
    assert r.status_code == 401


def test_google_login_401_on_a_bad_token(client: TestClient, monkeypatch):
    def boom(token):
        raise GoogleAuthError("forged")

    monkeypatch.setattr(auth_router, "verify_google_id_token", boom)
    r = client.post("/api/auth/google", json={"id_token": "bad"})
    assert r.status_code == 401


def test_google_login_503_when_disabled(client: TestClient, monkeypatch):
    def off(token):
        raise GoogleAuthUnavailable()

    monkeypatch.setattr(auth_router, "verify_google_id_token", off)
    r = client.post("/api/auth/google", json={"id_token": "x"})
    assert r.status_code == 503


def test_password_login_impossible_for_a_google_account(client: TestClient, fake_google):
    # Create a google account, then try the password form for it — must 401,
    # not 500 (a NULL hash used to crash passlib.verify).
    fake_google(email="pwtest@example.com")
    client.post("/api/auth/google", json={"id_token": "x"})
    r = client.post(
        "/api/auth/token", data={"username": "pwtest@example.com", "password": "anything"}
    )
    assert r.status_code == 401
