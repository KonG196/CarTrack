"""/backup bot command: on-demand, admin-only, and no longer auto-pushed."""

import asyncio
import datetime as dt
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiogram.types import Chat, Message

from app.bot import handlers, reminders
from app.config import settings

CHAT_ID = 42


class _Handle:
    """What Message.answer returns — supports the edit/delete the loader uses."""

    def __init__(self, entry):
        self._entry = entry

    async def edit_text(self, text, **kwargs):
        self._entry["text"] = text

    async def delete(self):
        self._entry["deleted"] = True


@pytest.fixture()
def replies(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    sent: list[dict] = []

    async def fake_answer(self, text: str = "", **kwargs):
        entry = {"text": text}
        sent.append(entry)
        return _Handle(entry)

    monkeypatch.setattr(Message, "answer", fake_answer)
    return sent


def _message() -> Message:
    msg = Message.model_construct(
        message_id=1,
        date=dt.datetime.now(dt.timezone.utc),
        chat=Chat.model_construct(id=CHAT_ID, type="private"),
        text="/backup",
    )
    return msg.as_(SimpleNamespace(id=1))  # bind a stand-in bot


def test_non_admin_cannot_backup(replies, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "BACKUP_TELEGRAM_CHAT_ID", "999")  # not this chat
    called = []
    monkeypatch.setattr(handlers.backup, "create_backup", lambda *a, **k: called.append(1))

    asyncio.run(handlers.cmd_backup(_message()))

    assert called == []  # never touched the DB dump
    assert any("admin" in r["text"].lower() for r in replies)


def test_backup_disabled_is_admin_only_too(replies, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "BACKUP_TELEGRAM_CHAT_ID", "")  # no admin configured
    called = []
    monkeypatch.setattr(handlers.backup, "create_backup", lambda *a, **k: called.append(1))

    asyncio.run(handlers.cmd_backup(_message()))
    assert called == []
    assert any("admin" in r["text"].lower() for r in replies)


def test_admin_gets_a_backup_on_demand(replies, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "BACKUP_TELEGRAM_CHAT_ID", str(CHAT_ID))  # this chat is admin
    made = []

    async def fake_send(path, bot=None):
        made.append(path)
        return True

    monkeypatch.setattr(handlers.backup, "create_backup", lambda *a, **k: Path("/tmp/x.db"))
    monkeypatch.setattr(handlers.backup, "rotate_backups", lambda *a, **k: 0)
    monkeypatch.setattr(handlers.backup, "send_backup_via_telegram", fake_send)

    asyncio.run(handlers.cmd_backup(_message()))

    assert made == [Path("/tmp/x.db")]  # the dump was created and delivered
    assert not any("Не вдалося" in r["text"] for r in replies)


def test_reminder_loop_no_longer_auto_backs_up() -> None:
    # The daily loop must not CALL run_daily_backup anymore — backups are pull-only.
    src = inspect.getsource(reminders.reminder_loop)
    assert "await run_daily_backup" not in src
