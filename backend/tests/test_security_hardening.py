"""Regression tests for the 2026-07-17 security hardening pass."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.requests import Request

from app.config import Settings
from app.ratelimit import client_ip
from tests.conftest import DEFAULT_PASSWORD


# --- config boot guards -----------------------------------------------------

def test_default_secret_key_is_refused():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SECRET_KEY="dev-secret-change-me")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SECRET_KEY="change-me-in-production")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SECRET_KEY="")


def test_real_secret_key_boots():
    s = Settings(_env_file=None, SECRET_KEY="a" * 40)
    assert s.SECRET_KEY == "a" * 40


def test_production_requires_smtp():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SECRET_KEY="a" * 40, ENV="production", SMTP_HOST="")
    # With SMTP set, production is fine.
    ok = Settings(_env_file=None, SECRET_KEY="a" * 40, ENV="production", SMTP_HOST="smtp.example.com")
    assert ok.is_production


# --- X-Forwarded-For is taken from the right (unspoofable hop) ---------------

def _req(xff: str | None, peer: str = "9.9.9.9") -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    return Request({"type": "http", "headers": headers, "client": (peer, 0)})


def test_client_ip_uses_last_forwarded_hop():
    # Client spoofed 1.1.1.1; the trusted proxy appended the real 2.2.2.2.
    assert client_ip(_req("1.1.1.1, 2.2.2.2")) == "2.2.2.2"


def test_client_ip_falls_back_to_peer_without_header():
    assert client_ip(_req(None)) == "9.9.9.9"


# --- SVG uploads are rejected (stored-XSS defense) --------------------------

def test_svg_document_is_rejected(
    client: TestClient, auth_headers: dict[str, str], make_car: Callable[..., dict]
):
    car = make_car()
    resp = client.post(
        f"/api/cars/{car['id']}/documents",
        headers=auth_headers,
        files={"file": ("evil.svg", b"<svg><script>alert(1)</script></svg>", "image/svg+xml")},
        data={"kind": "other", "title": "x"},
    )
    assert resp.status_code == 415, resp.text


def test_svg_photo_is_rejected(
    client: TestClient, auth_headers: dict[str, str], make_car: Callable[..., dict]
):
    car = make_car()
    log = client.post(
        f"/api/cars/{car['id']}/logs",
        headers=auth_headers,
        json={"type": "expense", "date": "2026-01-01", "odometer": 10001, "total_cost": 5},
    )
    assert log.status_code == 201, log.text
    resp = client.post(
        f"/api/logs/{log.json()['id']}/photos",
        headers=auth_headers,
        files={"file": ("evil.svg", b"<svg><script>alert(1)</script></svg>", "image/svg+xml")},
    )
    assert resp.status_code == 415, resp.text


# --- password-proof endpoints are rate limited ------------------------------

def test_account_delete_is_rate_limited(client: TestClient, auth_headers: dict[str, str]):
    # 5 wrong-password attempts are allowed (400), the 6th is throttled (429).
    for _ in range(5):
        r = client.request(
            "DELETE", "/api/auth/me", json={"password": "wrong"}, headers=auth_headers
        )
        assert r.status_code == 400, r.text
    blocked = client.request(
        "DELETE", "/api/auth/me", json={"password": "wrong"}, headers=auth_headers
    )
    assert blocked.status_code == 429, blocked.text
    # Even the correct password is now throttled — the limiter is on the endpoint.
    correct = client.request(
        "DELETE", "/api/auth/me", json={"password": DEFAULT_PASSWORD}, headers=auth_headers
    )
    assert correct.status_code == 429, correct.text
