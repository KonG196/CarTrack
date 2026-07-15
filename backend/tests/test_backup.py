"""Backup tests: hot SQLite copy, rotation, mocked Telegram delivery."""

import asyncio
import sqlite3
from pathlib import Path

import pytest

from app import backup
from app.config import settings


@pytest.fixture()
def source_db(tmp_path, monkeypatch) -> Path:
    db_path = tmp_path / "kapot_tracker.db"
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)")
    connection.execute("INSERT INTO users (email) VALUES ('user@example.com')")
    connection.commit()
    connection.close()
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_create_backup_produces_a_valid_sqlite_copy(source_db: Path, tmp_path) -> None:
    dest = tmp_path / "backups"
    result = backup.create_backup(dest_dir=dest)

    assert result.parent == dest
    assert result.name.startswith("kapot_tracker-")
    assert result.suffix == ".db"
    assert result.read_bytes().startswith(b"SQLite format 3")

    # the copy must be an openable database containing the users data
    copy = sqlite3.connect(result)
    try:
        rows = copy.execute("SELECT email FROM users").fetchall()
    finally:
        copy.close()
    assert rows == [("user@example.com",)]


def test_create_backup_uses_the_configured_backup_dir(
    source_db: Path, tmp_path, monkeypatch
) -> None:
    default_dir = tmp_path / "default-backups"
    monkeypatch.setattr(settings, "BACKUP_DIR", str(default_dir))
    result = backup.create_backup()
    assert result.parent == default_dir
    assert result.exists()


def test_rotate_backups_keeps_only_the_newest(tmp_path) -> None:
    for hour in range(6):
        (tmp_path / f"kapot_tracker-20260701-{hour:02d}0000.db").write_bytes(b"x")

    deleted = backup.rotate_backups(tmp_path, keep=2)

    assert deleted == 4
    remaining = sorted(path.name for path in tmp_path.iterdir())
    assert remaining == [
        "kapot_tracker-20260701-040000.db",
        "kapot_tracker-20260701-050000.db",
    ]


def test_rotate_backups_is_a_noop_below_the_limit(tmp_path) -> None:
    (tmp_path / "kapot_tracker-20260701-000000.db").write_bytes(b"x")
    assert backup.rotate_backups(tmp_path, keep=14) == 0
    assert len(list(tmp_path.iterdir())) == 1


def test_send_backup_skips_without_chat_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "BACKUP_TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "42:TEST")
    path = tmp_path / "kapot_tracker-20260701-000000.db"
    path.write_bytes(b"x")

    assert asyncio.run(backup.send_backup_via_telegram(path)) is False


def test_send_backup_sends_document_to_admin_chat(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "BACKUP_TELEGRAM_CHAT_ID", "12345")
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "42:TEST")
    path = tmp_path / "kapot_tracker-20260701-000000.db"
    path.write_bytes(b"x")

    sent: list[dict] = []

    class FakeSession:
        async def close(self) -> None:
            pass

    class FakeBot:
        def __init__(self, token: str) -> None:
            self.token = token
            self.session = FakeSession()

        async def send_document(self, chat_id, document, caption=None) -> None:
            sent.append({"chat_id": chat_id, "document": document, "caption": caption})

    monkeypatch.setattr(backup, "Bot", FakeBot)

    assert asyncio.run(backup.send_backup_via_telegram(path)) is True
    assert len(sent) == 1
    assert sent[0]["chat_id"] == "12345"
