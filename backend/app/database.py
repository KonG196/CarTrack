"""Database engine, session factory and FastAPI dependency."""

import json
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""


def _connect_args(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args(settings.DATABASE_URL),
    # Store JSON columns as readable UTF-8 instead of \uXXXX escapes so the
    # logbook search can LIKE-match Cyrillic text inside maintenance items.
    json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
)

if settings.DATABASE_URL.startswith("sqlite"):
    # SQLite ignores ON DELETE CASCADE unless foreign keys are enabled per
    # connection. Without this, deleting a car (or account) left its
    # obd_sessions/obd_metrics orphaned. Postgres enforces FKs natively.
    @event.listens_for(engine, "connect")
    def _sqlite_fk_pragma(dbapi_connection, _record):  # pragma: no cover - driver glue
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
