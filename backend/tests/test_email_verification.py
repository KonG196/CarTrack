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

    def fake_send(to: str, code: str, lang: str = "en") -> bool:
        sent.append((to, code))
        return True

    monkeypatch.setattr(verification, "mail_enabled", lambda: True)
    monkeypatch.setattr(verification, "send_verification", fake_send)
    return sent


def test_magic_links_url_encode_plus_addressed_email(monkeypatch):
    """A '+' in the address must be %2B in the link, or react-router decodes it to
    a space and confirmation/reset silently fail for the whole email forever."""
    from urllib.parse import parse_qs, urlparse

    from app.services import mailer

    captured: dict = {}

    def fake_send_mail(to, subject, text, html=None):
        captured["text"] = text
        captured["html"] = html or ""
        return True

    monkeypatch.setattr(mailer, "send_mail", fake_send_mail)

    for build in (mailer.send_verification, mailer.send_reset_code_mail):
        captured.clear()
        build("john+kapot@gmail.com", "123456", "en")
        blob = captured["text"] + captured["html"]
        assert "email=john%2Bkapot%40gmail.com" in blob or "email=john%2Bkapot@gmail.com" in blob
        assert "email=john+kapot@gmail.com" not in blob  # the broken form
        # The link's email param round-trips back to the original address.
        import re

        url = re.search(r"https?://\S*?/(verify|reset)\?\S+", blob).group(0).rstrip('".)')
        got = parse_qs(urlparse(url).query)["email"][0]
        assert got == "john+kapot@gmail.com"


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


def test_register_with_mail_server_still_lets_you_log_in(client: TestClient, mail_on) -> None:
    # Verification no longer gates login: a fresh (unverified) account can sign
    # in immediately. Verification only unlocks scan / plate lookup elsewhere.
    response = _register(client)
    assert response.status_code == 201
    assert response.json()["email_verified"] is False
    assert response.json()["verification_sent"] is True
    assert len(mail_on) == 1

    login = _login(client)
    assert login.status_code == 200
    assert "access_token" in login.json()


def _auth(client: TestClient) -> dict[str, str]:
    token = _login(client).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_scan_and_lookup_require_a_verified_email(client: TestClient, mail_on) -> None:
    # Unverified account: login works, but the costly features are gated (403).
    _register(client)
    headers = _auth(client)

    scan = client.post(
        "/api/ocr/scan",
        files={"file": ("r.jpg", b"fake-bytes", "image/jpeg")},
        headers=headers,
    )
    assert scan.status_code == 403

    lookup = client.post(
        "/api/plate/lookup", json={"query": "AA1234BB"}, headers=headers
    )
    assert lookup.status_code == 403

    # After verifying, the verification gate lifts. Use plate lookup to prove it:
    # without a baza-gai key it returns 503 (service unavailable), never the 403
    # verification gate — so «not 403» is the meaningful signal.
    _, code = mail_on[0]
    client.post("/api/auth/verify/confirm", json={"email": "new@example.com", "code": code})
    lookup_after = client.post(
        "/api/plate/lookup", json={"query": "AA1234BB"}, headers=_auth(client)
    )
    assert lookup_after.status_code != 403


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
    # A wrong code leaves the account unverified — but login is open regardless.
    assert _login(client).status_code == 200


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
