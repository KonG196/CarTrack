"""Server-side onboarding tours: /auth/me/tours/{name}."""

from fastapi.testclient import TestClient


def test_new_account_has_no_tours_seen(client: TestClient, auth_headers: dict):
    me = client.get("/api/auth/me", headers=auth_headers).json()
    assert me["tours_seen"] == []


def test_marking_a_tour_is_idempotent(client: TestClient, auth_headers: dict):
    r1 = client.post("/api/auth/me/tours/home", headers=auth_headers)
    assert r1.status_code == 200
    assert r1.json()["tours_seen"] == ["home"]

    # A second mark of the same tour doesn't duplicate it.
    r2 = client.post("/api/auth/me/tours/home", headers=auth_headers)
    assert r2.json()["tours_seen"] == ["home"]

    # A different tour is appended.
    r3 = client.post("/api/auth/me/tours/analytics", headers=auth_headers)
    assert set(r3.json()["tours_seen"]) == {"home", "analytics"}

    # And it survives a fresh /me fetch (persisted, not just echoed).
    me = client.get("/api/auth/me", headers=auth_headers).json()
    assert set(me["tours_seen"]) == {"home", "analytics"}


def test_unknown_tour_name_is_rejected(client: TestClient, auth_headers: dict):
    r = client.post("/api/auth/me/tours/not-a-real-tour", headers=auth_headers)
    assert r.status_code == 404


def test_tours_require_auth(client: TestClient):
    assert client.post("/api/auth/me/tours/home").status_code == 401
