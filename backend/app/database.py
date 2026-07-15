"""Database engine, session factory and FastAPI dependency."""

import json
from collections.abc import Generator

from sqlalchemy import create_engine
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

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
