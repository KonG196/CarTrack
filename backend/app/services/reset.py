"""Password reset via the linked Telegram bot.

The code is a DB-stored 6-digit secret (bcrypt-hashed, 10-minute TTL) —
deliberately NOT a JWT, so it can never be mistaken for an access token.
"""

from __future__ import annotations

import datetime as dt
import logging
import secrets

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_password, verify_password
from app.config import settings
from app.models import User
from app.services.mailer import mail_enabled, send_reset_code_mail

logger = logging.getLogger(__name__)

RESET_CODE_TTL_MINUTES = 10


def generate_reset_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


async def send_reset_code(chat_id: str, code: str) -> None:
    """Send the reset code to the user's linked Telegram chat.

    A missing bot token silently skips delivery: the request endpoint must
    answer 202 either way (no user enumeration, no Telegram dependency).
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        return
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"Код для скидання пароля Kapot Tracker: {code}\n"
                f"Діє {RESET_CODE_TTL_MINUTES} хвилин. "
                "Якщо це були не ви — просто проігноруйте це повідомлення."
            ),
        )
    finally:
        await bot.session.close()


async def initiate_reset(db: Session, email: str, channel: str | None = None) -> None:
    """Store a hashed reset code and deliver it.

    ``channel`` is what the user picked; it is honoured when that channel can
    actually reach the account and quietly swapped for the other when it
    cannot. Silently does nothing for unknown emails, or when neither channel
    can reach the account — a code nobody can receive is only attack surface.
    The caller answers 202 regardless, so responses never reveal whether an
    account exists.
    """
    normalized = email.strip().lower()
    user = db.execute(select(User).where(User.email == normalized)).scalar_one_or_none()
    if user is None:
        return
    if not user.telegram_chat_id and not mail_enabled():
        return
    code = generate_reset_code()
    user.reset_code_hash = hash_password(code)
    user.reset_code_expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
        minutes=RESET_CODE_TTL_MINUTES
    )
    db.commit()
    # The pick is honoured when that channel can reach the account, and quietly
    # swapped when it cannot: silence would be worse than the other channel.
    use_telegram = bool(user.telegram_chat_id) and channel != "email"
    try:
        if use_telegram:
            await send_reset_code(user.telegram_chat_id, code)
        elif mail_enabled():
            send_reset_code_mail(user.email, code)
        elif user.telegram_chat_id:
            await send_reset_code(user.telegram_chat_id, code)
    except Exception:  # noqa: BLE001 - delivery failures must not break the 202
        logger.warning("Failed to send a reset code", exc_info=True)


def confirm_reset(db: Session, email: str, code: str, new_password: str) -> bool:
    """Set a new password when the code matches and has not expired.

    Returns False for every failure mode alike (unknown email, no pending
    code, expired, mismatch) so the endpoint cannot leak which one it was.
    NOTE: previously issued JWT access tokens stay valid until their own
    expiry — tokens are stateless and a reset does not revoke sessions.
    """
    normalized = email.strip().lower()
    user = db.execute(select(User).where(User.email == normalized)).scalar_one_or_none()
    if user is None or user.reset_code_hash is None or user.reset_code_expires_at is None:
        return False
    expires_at = user.reset_code_expires_at
    if expires_at.tzinfo is None:
        # DateTime columns come back naive from the driver; they store UTC.
        expires_at = expires_at.replace(tzinfo=dt.timezone.utc)
    if expires_at < dt.datetime.now(dt.timezone.utc):
        return False
    if not verify_password(code, user.reset_code_hash):
        return False
    user.hashed_password = hash_password(new_password)
    user.reset_code_hash = None
    user.reset_code_expires_at = None
    db.commit()
    return True
