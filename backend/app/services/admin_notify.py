"""Owner alerts for the four moments that mean the app is being used for real:
a new signup, a first car, a first verified address, a first OCR scan.

Each helper is a one-shot: it flips the matching `admin_notified_*` flag on the
user, commits, then sends the mail. Committing the flag *before* the send means a
dead SMTP server or a crash costs at most one missed alert, never a duplicate on
the next request. Everything is best-effort — a mail failure must never surface
to the user or roll back the action that triggered it, so the whole body runs
under a broad except that only logs.

These letters go to the owner (settings.ADMIN_EMAIL), not to the user, so the
copy is plain Ukrainian and internal — no branding niceties beyond the shared
template. With no ADMIN_EMAIL set, the whole thing is a no-op.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Car, User
from app.services.mailer import _render_email, send_mail

logger = logging.getLogger(__name__)

# App URL for the little "open the app" convenience link at the foot of each
# note — the owner reads these on a phone and may want to jump straight in.
_APP_URL = settings.PUBLIC_URL.rstrip("/") or "https://kapot.app"


def _who(user: User) -> str:
    """A recognisable one-liner for the user: name plus the real address."""
    name = (user.display_name or "").strip()
    return f"{name} ({user.email})" if name else user.email


def _send_admin(subject: str, heading: str, lede: str, note: str | None = None) -> bool:
    """Render and send one owner note. Returns False when admin mail is off."""
    to = (settings.ADMIN_EMAIL or "").strip()
    if not to:
        return False
    text = f"{heading}\n\n{lede}"
    if note:
        text += f"\n\n{note}"
    return send_mail(
        to,
        subject,
        text,
        html=_render_email(
            lang="uk",
            heading=heading,
            lede=lede,
            button=("Відкрити Kapot", _APP_URL),
            note=note,
        ),
    )


def notify_new_signup(db: Session, user: User) -> None:
    """A brand-new account was created."""
    if user.admin_notified_signup:
        return
    try:
        user.admin_notified_signup = True
        db.commit()
        _send_admin(
            subject="Kapot: новий користувач",
            heading="Новий користувач",
            lede=f"Щойно зареєструвався: {_who(user)}.",
        )
    except Exception:  # noqa: BLE001 — an alert must never break signup
        logger.exception("admin signup notification failed for user %s", user.id)


def notify_first_car(db: Session, user: User, car: Car) -> None:
    """The user added their first car."""
    if user.admin_notified_first_car:
        return
    try:
        user.admin_notified_first_car = True
        db.commit()
        car_line = " ".join(
            str(part)
            for part in (car.brand, car.model, car.year, car.fuel_type)
            if part
        )
        _send_admin(
            subject="Kapot: перша машина",
            heading="Перша машина додана",
            lede=f"{_who(user)} додав(-ла) першу машину.",
            note=f"Авто: {car_line}." if car_line else None,
        )
    except Exception:  # noqa: BLE001
        logger.exception("admin first-car notification failed for user %s", user.id)


def notify_first_verified(db: Session, user: User) -> None:
    """The user verified their email address for the first time."""
    if user.admin_notified_verified:
        return
    try:
        user.admin_notified_verified = True
        db.commit()
        _send_admin(
            subject="Kapot: підтверджена пошта",
            heading="Пошту підтверджено",
            lede=f"{_who(user)} вперше підтвердив(-ла) email.",
        )
    except Exception:  # noqa: BLE001
        logger.exception("admin verify notification failed for user %s", user.id)


def notify_first_ocr(db: Session, user: User, kind: str = "чек") -> None:
    """The user ran OCR (receipt or work order) for the first time."""
    if user.admin_notified_first_ocr:
        return
    try:
        user.admin_notified_first_ocr = True
        db.commit()
        _send_admin(
            subject="Kapot: перше сканування",
            heading="Перше сканування (OCR)",
            lede=f"{_who(user)} вперше скористав(-ла)ся розпізнаванням.",
            note=f"Тип: {kind}." if kind else None,
        )
    except Exception:  # noqa: BLE001
        logger.exception("admin OCR notification failed for user %s", user.id)
