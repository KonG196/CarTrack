"""DELETE /api/auth/me — irreversible account deletion."""

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from tests.conftest import DEFAULT_EMAIL, DEFAULT_PASSWORD


def test_wrong_password_is_rejected_and_account_survives(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.request(
        "DELETE", "/api/auth/me", json={"password": "not-my-password"}, headers=auth_headers
    )
    assert resp.status_code == 400, resp.text
    # Still logged in, still there.
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 200


def test_correct_password_deletes_account_and_invalidates_session(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.request(
        "DELETE", "/api/auth/me", json={"password": DEFAULT_PASSWORD}, headers=auth_headers
    )
    assert resp.status_code == 204, resp.text
    # The token now points at a user that no longer exists.
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 401


def test_deletion_cascades_cars_and_frees_the_email(
    client: TestClient,
    auth_headers: dict[str, str],
    make_car: Callable[..., dict],
) -> None:
    make_car()
    assert len(client.get("/api/cars", headers=auth_headers).json()) == 1

    resp = client.request(
        "DELETE", "/api/auth/me", json={"password": DEFAULT_PASSWORD}, headers=auth_headers
    )
    assert resp.status_code == 204, resp.text

    # The email is free again — proof the row is gone, not just detached.
    again = client.post(
        "/api/auth/register", json={"email": DEFAULT_EMAIL, "password": DEFAULT_PASSWORD}
    )
    assert again.status_code == 201, again.text
    # And the fresh account inherits none of the old cars.
    token = client.post(
        "/api/auth/token", data={"username": DEFAULT_EMAIL, "password": DEFAULT_PASSWORD}
    ).json()["access_token"]
    fresh = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/cars", headers=fresh).json() == []


def test_deletion_wipes_the_users_upload_directory(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path))
    user_id = client.get("/api/auth/me", headers=auth_headers).json()["id"]
    user_dir = tmp_path / str(user_id)
    user_dir.mkdir()
    (user_dir / "receipt.jpg").write_bytes(b"not really a jpg")

    resp = client.request(
        "DELETE", "/api/auth/me", json={"password": DEFAULT_PASSWORD}, headers=auth_headers
    )
    assert resp.status_code == 204, resp.text
    assert not user_dir.exists()


def test_missing_upload_directory_is_not_an_error(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # A user who never uploaded anything has no directory — deletion must still
    # succeed rather than trip over the missing path.
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path))
    resp = client.request(
        "DELETE", "/api/auth/me", json={"password": DEFAULT_PASSWORD}, headers=auth_headers
    )
    assert resp.status_code == 204, resp.text
