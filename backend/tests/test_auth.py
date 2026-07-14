"""Auth endpoint tests: register, login, me, failure modes."""

from fastapi.testclient import TestClient


def test_register_returns_user(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={"email": "new@example.com", "password": "secret123"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert isinstance(body["id"], int)
    assert "created_at" in body
    assert "password" not in body
    assert "hashed_password" not in body


def test_register_duplicate_email_rejected(client: TestClient) -> None:
    payload = {"email": "dup@example.com", "password": "secret123"}
    assert client.post("/api/auth/register", json=payload).status_code == 201
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code in (400, 409)
    assert "detail" in response.json()


def test_register_invalid_email_422(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register", json={"email": "not-an-email", "password": "secret123"}
    )
    assert response.status_code == 422


def test_login_and_me(client: TestClient) -> None:
    client.post(
        "/api/auth/register",
        json={"email": "login@example.com", "password": "secret123"},
    )
    response = client.post(
        "/api/auth/token",
        data={"username": "login@example.com", "password": "secret123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]

    me = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "login@example.com"


def test_login_wrong_password_401(client: TestClient) -> None:
    client.post(
        "/api/auth/register",
        json={"email": "wrongpw@example.com", "password": "secret123"},
    )
    response = client.post(
        "/api/auth/token",
        data={"username": "wrongpw@example.com", "password": "not-the-password"},
    )
    assert response.status_code == 401
    assert "detail" in response.json()


def test_login_unknown_user_401(client: TestClient) -> None:
    response = client.post(
        "/api/auth/token",
        data={"username": "ghost@example.com", "password": "secret123"},
    )
    assert response.status_code == 401


def test_me_without_token_401(client: TestClient) -> None:
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_with_garbage_token_401(client: TestClient) -> None:
    response = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer garbage.token.here"}
    )
    assert response.status_code == 401
