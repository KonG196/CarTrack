"""Delivery for the owner's admin alerts over a DEDICATED Telegram bot.

Not email (that burned the free SMTP tier) and not the main bot (users share
it): a separate bot, configured via ADMIN_BOT_TOKEN + ADMIN_TELEGRAM_CHAT_ID,
that only ever messages the owner.

A plain synchronous httpx POST to the Telegram Bot API — no aiogram, no event
loop — so it drops straight into the sync endpoint code (register / create_car /
verify) as well as the OCR path (run off-thread there). Best-effort: any failure
is swallowed and logged, never raised, so a down Telegram never touches the user
action that triggered the alert. Cost is one short outbound request per rare
event — negligible for the server.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Telegram caps a text message at 4096 chars and a photo caption at 1024. Keep a
# margin so an unusually long note never gets rejected wholesale.
_TEXT_LIMIT = 4000
_CAPTION_LIMIT = 1000
_TIMEOUT = 8.0


def admin_telegram_enabled() -> bool:
    return bool(settings.ADMIN_BOT_TOKEN and settings.ADMIN_TELEGRAM_CHAT_ID)


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{settings.ADMIN_BOT_TOKEN}/{method}"


def send_admin_message(
    text: str, photo: tuple[str, bytes, str] | None = None
) -> bool:
    """Send one alert to the owner. Returns False when admin Telegram is off or
    the send fails. `photo` is (filename, bytes, content_type) — sent as a photo
    with `text` as its caption (e.g. the scanned receipt on a first-OCR alert).
    """
    if not admin_telegram_enabled():
        return False
    chat_id = settings.ADMIN_TELEGRAM_CHAT_ID
    try:
        if photo is not None:
            filename, data, content_type = photo
            return _send_photo(chat_id, text, filename, data, content_type)
        resp = httpx.post(
            _api("sendMessage"),
            json={"chat_id": chat_id, "text": text[:_TEXT_LIMIT]},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return True
    except Exception:  # noqa: BLE001 — an alert must never break the caller
        logger.warning("admin Telegram send failed", exc_info=True)
        return False


def _send_photo(
    chat_id: str, caption: str, filename: str, data: bytes, content_type: str
) -> bool:
    resp = httpx.post(
        _api("sendPhoto"),
        data={"chat_id": chat_id, "caption": caption[:_CAPTION_LIMIT]},
        files={"photo": (filename, data, content_type)},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return True
