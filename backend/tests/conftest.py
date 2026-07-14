"""Shared pytest fixtures: isolated in-memory database + auth helpers."""

from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

DEFAULT_EMAIL = "user@example.com"
DEFAULT_PASSWORD = "secret123"


@pytest.fixture()
def db_engine() -> Generator[Engine, None, None]:
    """A fresh in-memory SQLite engine with the full schema per test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session_factory(db_engine: Engine) -> sessionmaker:
    """Session factory on the test engine, for direct (non-HTTP) DB access."""
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
    """Factory registering a user and returning Bearer auth headers."""

    def _make_user(
        email: str = DEFAULT_EMAIL, password: str = DEFAULT_PASSWORD
    ) -> dict[str, str]:
        response = client.post(
            "/api/auth/register", json={"email": email, "password": password}
        )
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
    """Auth headers for a default registered user."""
    return make_user()


@pytest.fixture()
def make_car(client: TestClient, auth_headers: dict[str, str]) -> Callable[..., dict]:
    """Factory creating a car (default user unless headers are given)."""

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
