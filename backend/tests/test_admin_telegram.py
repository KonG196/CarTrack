"""The admin Telegram sender: disabled without config, best-effort on failure,
and posts to the right Bot API method (message vs photo)."""

from __future__ import annotations

import pytest

from app.config import settings
from app.services import admin_telegram


def _configure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ADMIN_BOT_TOKEN", "TESTTOKEN")
    monkeypatch.setattr(settings, "ADMIN_TELEGRAM_CHAT_ID", "12345")


def test_disabled_without_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ADMIN_BOT_TOKEN", "")
    monkeypatch.setattr(settings, "ADMIN_TELEGRAM_CHAT_ID", "")
    assert admin_telegram.admin_telegram_enabled() is False
    # Returns False and never touches the network.
    assert admin_telegram.send_admin_message("hi") is False


def test_sends_text_message(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch)
    calls: list[dict] = []

    class FakeResp:
        def raise_for_status(self):
            return None

    def fake_post(url, json=None, data=None, files=None, timeout=None):
        calls.append({"url": url, "json": json, "data": data, "files": files})
        return FakeResp()

    monkeypatch.setattr(admin_telegram.httpx, "post", fake_post)
    assert admin_telegram.send_admin_message("hello owner") is True
    assert len(calls) == 1
    assert calls[0]["url"].endswith("/sendMessage")
    assert calls[0]["json"]["chat_id"] == "12345"
    assert calls[0]["json"]["text"] == "hello owner"


def test_sends_photo_with_caption(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch)
    calls: list[dict] = []

    class FakeResp:
        def raise_for_status(self):
            return None

    def fake_post(url, json=None, data=None, files=None, timeout=None):
        calls.append({"url": url, "data": data, "files": files})
        return FakeResp()

    monkeypatch.setattr(admin_telegram.httpx, "post", fake_post)
    photo = ("receipt.jpg", b"\xff\xd8\xffdata", "image/jpeg")
    assert admin_telegram.send_admin_message("scanned", photo=photo) is True
    assert calls[0]["url"].endswith("/sendPhoto")
    assert calls[0]["data"]["caption"] == "scanned"
    assert calls[0]["files"]["photo"] == photo


def test_send_failure_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(admin_telegram.httpx, "post", boom)
    # Must return False, not raise.
    assert admin_telegram.send_admin_message("hi") is False
