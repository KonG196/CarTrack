"""Outgoing email over plain SMTP.

Sending is optional on purpose: with no SMTP_HOST the app must stay fully
usable offline, so callers treat a False return as "no mail was sent" rather
than an error. Whether that is acceptable is the caller's decision — the
registration flow, for one, auto-verifies instead of stranding the account.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def mail_enabled() -> bool:
    return bool(settings.SMTP_HOST)


def send_mail(to: str, subject: str, body: str) -> bool:
    """Send a plain-text message. Returns False when mail is off or fails."""
    if not mail_enabled():
        logger.info("SMTP disabled, would send to %s: %s", to, subject)
        return False

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
            if settings.SMTP_STARTTLS:
                smtp.starttls()
            if settings.SMTP_USER:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(message)
        return True
    except (smtplib.SMTPException, OSError):
        # A dead mail server must not take the request down with it: the caller
        # decides what an unsent letter means.
        logger.exception("SMTP send to %s failed", to)
        return False


def send_verification(to: str, code: str) -> bool:
    link = f"{settings.PUBLIC_URL.rstrip('/')}/verify?email={to}&code={code}"
    return send_mail(
        to,
        "Kapot Tracker — підтвердження пошти",
        f"Вітаємо в Kapot Tracker!\n\n"
        f"Код підтвердження: {code}\n\n"
        f"Або просто перейдіть за посиланням:\n{link}\n\n"
        f"Код дійсний {settings.VERIFY_CODE_EXPIRE_HOURS} год. "
        f"Якщо ви не реєструвалися — просто проігноруйте цей лист.",
    )


def send_reset_code_mail(to: str, code: str) -> bool:
    return send_mail(
        to,
        "Kapot Tracker — відновлення пароля",
        f"Код для зміни пароля: {code}\n\n"
        f"Код дійсний 10 хвилин і працює один раз.\n"
        f"Якщо ви не просили зміну пароля — просто проігноруйте цей лист.",
    )
