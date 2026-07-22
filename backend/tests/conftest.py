"""Shared pytest fixtures: isolated in-memory database + auth helpers."""

import json
from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.routers.plate import lookup_limiter
from app.routers.auth import (
    login_limiter,
    register_limiter,
    reset_confirm_limiter,
    reset_request_limiter,
    sensitive_limiter,
    verify_resend_limiter,
)

DEFAULT_EMAIL = "user@example.com"
DEFAULT_PASSWORD = "secret123"


@pytest.fixture(autouse=True)
def _no_outside_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never touch the outside world from a test.

    Settings are read from .env, so a developer with real credentials had the
    suite mail verification codes to example.com — the bounces landed in their
    own inbox — and send every unreadable receipt to Gemini for real money and
    real seconds. A test that wants either path patches it explicitly.
    """
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "OCR_SPACE_API_KEY", "")
    monkeypatch.setattr(settings, "OCR_SPACE_USE_DEMO_KEY", False)
    # Cleared like the rest: a real key in .env (added for local plate-lookup
    # testing) must not leak into the suite as live calls, and the
    # «disabled without a key» test depends on it being empty.
    monkeypatch.setattr(settings, "BAZA_GAI_API_KEY", "")


@pytest.fixture(autouse=True)
def _clear_rate_limiters() -> None:
    """Rate-limiter state is process-global; every test starts with a clean slate
    (all TestClient requests share one client IP, so tests would otherwise
    exhaust the per-IP register budget across the suite)."""
    for limiter in (
        login_limiter,
        register_limiter,
        reset_request_limiter,
        reset_confirm_limiter,
        verify_resend_limiter,
        sensitive_limiter,
        lookup_limiter,
    ):
        limiter.clear()


@pytest.fixture()
def db_engine() -> Generator[Engine, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        # Match the app engine: JSON stored as readable UTF-8 (search relies
        # on LIKE over the serialized maintenance items).
        json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session_factory(db_engine: Engine) -> sessionmaker:
    return sessionmaker(bind=db_engine, autocommit=False, autoflush=False)


@pytest.fixture()
def client(db_session_factory: sessionmaker) -> Generator[TestClient, None, None]:
    """A TestClient backed by the per-test in-memory SQLite schema.

    The client is deliberately not used as a context manager so the app
    lifespan (which would create tables on the real engine) never runs;
    tables are created directly on the throwaway test engine instead.
    """

    def override_get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def make_user(client: TestClient) -> Callable[..., dict[str, str]]:

    def _make_user(
        email: str = DEFAULT_EMAIL, password: str = DEFAULT_PASSWORD, language: str | None = None
    ) -> dict[str, str]:
        body = {"email": email, "password": password}
        if language is not None:
            body["language"] = language
        response = client.post("/api/auth/register", json=body)
        assert response.status_code == 201, response.text
        response = client.post(
            "/api/auth/token", data={"username": email, "password": password}
        )
        assert response.status_code == 200, response.text
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _make_user


@pytest.fixture()
def auth_headers(make_user: Callable[..., dict[str, str]]) -> dict[str, str]:
    return make_user()


@pytest.fixture()
def make_car(client: TestClient, auth_headers: dict[str, str]) -> Callable[..., dict]:

    def _make_car(headers: dict[str, str] | None = None, **overrides) -> dict:
        payload = {
            "brand": "Toyota",
            "model": "Corolla",
            "year": 2018,
            "fuel_type": "petrol",
            "current_odometer": 10000,
        }
        payload.update(overrides)
        response = client.post(
            "/api/cars", json=payload, headers=headers or auth_headers
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _make_car
