"""The superadmin panel: access gating, user edits, status toggles, link
generation, deletion, and the safety rails that stop a superadmin from locking
themselves out. Each mutation must also leave one audit row."""

from __future__ import annotations

from typing import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.models import AdminAuditLog, User


@pytest.fixture
def make_superadmin(
    client: TestClient,
    make_user: Callable[..., dict[str, str]],
    db_session_factory: sessionmaker,
) -> Callable[..., dict[str, str]]:
    """Register a user and promote it to superadmin directly in the DB, then
    return fresh auth headers (login again so the token is post-promotion)."""

    def _make(email: str = "admin@example.com", password: str = "password123") -> dict[str, str]:
        make_user(email=email, password=password)
        with db_session_factory() as db:
            user = db.execute(select(User).where(User.email == email)).scalar_one()
            user.is_superadmin = True
            db.commit()
        resp = client.post(
            "/api/auth/token", data={"username": email, "password": password}
        )
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _make


def _audit_count(db_session_factory: sessionmaker) -> int:
    with db_session_factory() as db:
        return db.scalar(select(func.count(AdminAuditLog.id))) or 0


# ── access gating ────────────────────────────────────────────────────────────


def test_non_admin_is_forbidden(client: TestClient, auth_headers: dict) -> None:
    for method, path in [
        ("get", "/api/admin/users"),
        ("get", "/api/admin/audit"),
        ("get", "/api/admin/users/1"),
    ]:
        resp = getattr(client, method)(path, headers=auth_headers)
        assert resp.status_code == 403, path


def test_anonymous_is_unauthorized(client: TestClient) -> None:
    assert client.get("/api/admin/users").status_code == 401


def test_admin_can_list_users(
    client: TestClient, make_superadmin, make_user
) -> None:
    admin = make_superadmin()
    make_user(email="alice@example.com")
    make_user(email="bob@example.com")
    resp = client.get("/api/admin/users", headers=admin)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 3
    emails = {u["email"] for u in body["users"]}
    assert {"alice@example.com", "bob@example.com", "admin@example.com"} <= emails


def test_search_filters_users(client: TestClient, make_superadmin, make_user) -> None:
    admin = make_superadmin()
    make_user(email="findme@example.com")
    resp = client.get("/api/admin/users?q=findme", headers=admin)
    assert resp.status_code == 200
    users = resp.json()["users"]
    assert len(users) == 1 and users[0]["email"] == "findme@example.com"


# ── editing ──────────────────────────────────────────────────────────────────


def _uid(client: TestClient, admin: dict, email: str) -> int:
    resp = client.get(f"/api/admin/users?q={email}", headers=admin)
    return resp.json()["users"][0]["id"]


def test_edit_user_fields_and_audits(
    client: TestClient, make_superadmin, make_user, db_session_factory
) -> None:
    admin = make_superadmin()
    make_user(email="edit@example.com")
    uid = _uid(client, admin, "edit@example.com")
    before = _audit_count(db_session_factory)
    resp = client.patch(
        f"/api/admin/users/{uid}",
        json={"display_name": "Renamed", "currency": "eur"},
        headers=admin,
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["display_name"] == "Renamed"
    assert resp.json()["user"]["currency"] == "EUR"
    assert _audit_count(db_session_factory) == before + 1


def test_edit_to_taken_email_rejected(
    client: TestClient, make_superadmin, make_user
) -> None:
    admin = make_superadmin()
    make_user(email="a@example.com")
    make_user(email="b@example.com")
    uid = _uid(client, admin, "a@example.com")
    resp = client.patch(
        f"/api/admin/users/{uid}", json={"email": "b@example.com"}, headers=admin
    )
    assert resp.status_code == 400


# ── status toggles + safety rails ────────────────────────────────────────────


def test_verify_and_unverify(client: TestClient, make_superadmin, make_user) -> None:
    admin = make_superadmin()
    make_user(email="v@example.com")
    uid = _uid(client, admin, "v@example.com")
    # Off then on, so both directions are exercised (register auto-verifies here).
    off = client.post(
        f"/api/admin/users/{uid}/status", json={"email_verified": False}, headers=admin
    )
    assert off.status_code == 200 and off.json()["user"]["email_verified"] is False
    on = client.post(
        f"/api/admin/users/{uid}/status", json={"email_verified": True}, headers=admin
    )
    assert on.status_code == 200 and on.json()["user"]["email_verified"] is True


def test_block_requires_reason(client: TestClient, make_superadmin, make_user) -> None:
    admin = make_superadmin()
    make_user(email="block@example.com")
    uid = _uid(client, admin, "block@example.com")
    r = client.post(
        f"/api/admin/users/{uid}/status", json={"blocked": True}, headers=admin
    )
    assert r.status_code == 400  # no reason


def test_block_severs_session_and_login(
    client: TestClient, make_superadmin, make_user, db_session_factory
) -> None:
    admin = make_superadmin()
    victim = make_user(email="victim@example.com", password="password123")
    uid = _uid(client, admin, "victim@example.com")
    # Victim has a working session right now.
    assert client.get("/api/auth/me", headers=victim).status_code == 200

    r = client.post(
        f"/api/admin/users/{uid}/status",
        json={"blocked": True, "blocked_reason": "спам"},
        headers=admin,
    )
    assert r.status_code == 200 and r.json()["user"]["blocked"] is True

    # Live token now dead (token_version bump makes it fail validation → 401),
    # and a fresh login is refused with the reason (→ 403).
    assert client.get("/api/auth/me", headers=victim).status_code != 200
    login = client.post(
        "/api/auth/token",
        data={"username": "victim@example.com", "password": "password123"},
    )
    assert login.status_code == 403
    assert "спам" in login.json()["detail"]

    # Unblock restores login.
    client.post(
        f"/api/admin/users/{uid}/status", json={"blocked": False}, headers=admin
    )
    login2 = client.post(
        "/api/auth/token",
        data={"username": "victim@example.com", "password": "password123"},
    )
    assert login2.status_code == 200


def test_cannot_block_demote_or_delete_self(
    client: TestClient, make_superadmin, db_session_factory
) -> None:
    admin = make_superadmin(email="self@example.com")
    uid = _uid(client, admin, "self@example.com")
    assert (
        client.post(
            f"/api/admin/users/{uid}/status",
            json={"blocked": True, "blocked_reason": "x"},
            headers=admin,
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"/api/admin/users/{uid}/status",
            json={"is_superadmin": False},
            headers=admin,
        ).status_code
        == 400
    )
    assert client.delete(f"/api/admin/users/{uid}", headers=admin).status_code == 400


# ── link generation ──────────────────────────────────────────────────────────


def test_reset_and_verify_links(client: TestClient, make_superadmin, make_user) -> None:
    admin = make_superadmin()
    make_user(email="links@example.com")
    uid = _uid(client, admin, "links@example.com")

    r1 = client.post(f"/api/admin/users/{uid}/reset-link", headers=admin)
    assert r1.status_code == 200
    assert "/reset?email=links%40example.com&code=" in r1.json()["link"]

    r2 = client.post(f"/api/admin/users/{uid}/verify-link", headers=admin)
    assert r2.status_code == 200
    assert "/verify?email=links%40example.com&code=" in r2.json()["link"]


def test_generated_reset_link_actually_resets(
    client: TestClient, make_superadmin, make_user
) -> None:
    """The code embedded in an admin-generated reset link must be the real one:
    confirming it sets a new password the user can then log in with."""
    from urllib.parse import parse_qs, urlparse

    admin = make_superadmin()
    make_user(email="realreset@example.com", password="password123")
    uid = _uid(client, admin, "realreset@example.com")
    link = client.post(f"/api/admin/users/{uid}/reset-link", headers=admin).json()["link"]
    code = parse_qs(urlparse(link).query)["code"][0]

    resp = client.post(
        "/api/auth/reset/confirm",
        json={
            "email": "realreset@example.com",
            "code": code,
            "new_password": "brandnew99",
        },
    )
    assert resp.status_code == 200, resp.text
    login = client.post(
        "/api/auth/token",
        data={"username": "realreset@example.com", "password": "brandnew99"},
    )
    assert login.status_code == 200


# ── deletion ─────────────────────────────────────────────────────────────────


def test_delete_user_and_audit_survives(
    client: TestClient, make_superadmin, make_user, db_session_factory
) -> None:
    admin = make_superadmin()
    make_user(email="doomed@example.com")
    uid = _uid(client, admin, "doomed@example.com")
    resp = client.delete(f"/api/admin/users/{uid}", headers=admin)
    assert resp.status_code == 204
    # User gone.
    assert client.get(f"/api/admin/users/{uid}", headers=admin).status_code == 404
    # The audit row survives the delete and keeps the email verbatim, so the
    # trail stays readable. (target_user_id goes NULL via ON DELETE SET NULL,
    # which needs PRAGMA foreign_keys=ON — enforced on the prod engine, not the
    # bare test engine — so target_email is the durable guarantee we assert.)
    with db_session_factory() as db:
        row = db.execute(
            select(AdminAuditLog).where(AdminAuditLog.action == "delete_user")
        ).scalar_one()
        assert row.target_email == "doomed@example.com"


def test_audit_feed_lists_actions(
    client: TestClient, make_superadmin, make_user
) -> None:
    admin = make_superadmin()
    make_user(email="feed@example.com")
    uid = _uid(client, admin, "feed@example.com")
    # Mail is off in tests, so registration auto-verifies — toggle OFF to make a
    # real change the audit will record.
    client.post(
        f"/api/admin/users/{uid}/status", json={"email_verified": False}, headers=admin
    )
    resp = client.get("/api/admin/audit", headers=admin)
    assert resp.status_code == 200
    actions = {r["action"] for r in resp.json()}
    assert "unverify" in actions
