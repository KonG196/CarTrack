"""Rate limiting: sliding-window unit behaviour + 429 wiring on auth endpoints."""

from fastapi.testclient import TestClient

from app.ratelimit import RateLimiter

EMAIL = "victim@example.com"
PASSWORD = "secret123"


# RateLimiter unit tests (injectable clock)


def test_limiter_blocks_after_limit() -> None:
    limiter = RateLimiter(limit=3, window_seconds=60)
    assert limiter.check("k", now=0.0)
    assert limiter.check("k", now=1.0)
    assert limiter.check("k", now=2.0)
    assert not limiter.check("k", now=3.0)


def test_limiter_window_slides() -> None:
    limiter = RateLimiter(limit=2, window_seconds=60)
    assert limiter.check("k", now=0.0)
    assert limiter.check("k", now=10.0)
    assert not limiter.check("k", now=59.0)
    # the first attempt (t=0) has left the 60s window
    assert limiter.check("k", now=61.0)


def test_limiter_reset_clears_key() -> None:
    limiter = RateLimiter(limit=1, window_seconds=60)
    assert limiter.check("k", now=0.0)
    assert not limiter.check("k", now=1.0)
    limiter.reset("k")
    assert limiter.check("k", now=2.0)


def test_limiter_keys_are_independent() -> None:
    limiter = RateLimiter(limit=1, window_seconds=60)
    assert limiter.check("a", now=0.0)
    assert not limiter.check("a", now=1.0)
    assert limiter.check("b", now=1.0)


def test_limiter_retry_after_counts_down() -> None:
    limiter = RateLimiter(limit=1, window_seconds=60)
    limiter.check("k", now=0.0)
    assert limiter.retry_after("k", now=10.0) == 50
    assert limiter.retry_after("k", now=59.5) == 1


# Endpoint wiring


def _register(client: TestClient, email: str = EMAIL) -> None:
    response = client.post(
        "/api/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text


def _login(client: TestClient, email: str = EMAIL, password: str = PASSWORD):
    return client.post("/api/auth/token", data={"username": email, "password": password})


def test_sixth_login_attempt_is_429(client: TestClient) -> None:
    _register(client)
    for _ in range(5):
        assert _login(client, password="wrong-password").status_code == 401

    response = _login(client)  # correct password, but the limit is spent
    assert response.status_code == 429
    assert response.json()["detail"] == "Забагато спроб. Спробуйте пізніше."
    assert int(response.headers["retry-after"]) >= 1


def test_successful_login_resets_the_counter(client: TestClient) -> None:
    _register(client)
    for _ in range(4):
        assert _login(client, password="wrong-password").status_code == 401
    assert _login(client).status_code == 200  # success resets the window

    # a full fresh budget: five more failures stay 401, not 429
    for _ in range(5):
        assert _login(client, password="wrong-password").status_code == 401


def test_login_limit_is_per_email(client: TestClient) -> None:
    _register(client, "one@example.com")
    _register(client, "two@example.com")
    for _ in range(5):
        assert _login(client, "one@example.com", "wrong").status_code == 401
    assert _login(client, "one@example.com", "wrong").status_code == 429
    # a different email from the same IP is not affected
    assert _login(client, "two@example.com", "wrong").status_code == 401


def test_fourth_register_from_one_ip_is_429(client: TestClient) -> None:
    for index in range(3):
        _register(client, f"fresh{index}@example.com")
    response = client.post(
        "/api/auth/register",
        json={"email": "fresh3@example.com", "password": PASSWORD},
    )
    assert response.status_code == 429
    assert "retry-after" in response.headers


def test_fourth_reset_request_is_429(client: TestClient) -> None:
    for _ in range(3):
        assert (
            client.post("/api/auth/reset/request", json={"email": EMAIL}).status_code
            == 202
        )
    response = client.post("/api/auth/reset/request", json={"email": EMAIL})
    assert response.status_code == 429
    assert "retry-after" in response.headers


def test_sixth_reset_confirm_is_429(client: TestClient) -> None:
    payload = {"email": EMAIL, "code": "123456", "new_password": "newsecret123"}
    for _ in range(5):
        assert client.post("/api/auth/reset/confirm", json=payload).status_code == 400
    response = client.post("/api/auth/reset/confirm", json=payload)
    assert response.status_code == 429
    assert response.json()["detail"] == "Забагато спроб. Спробуйте пізніше."
