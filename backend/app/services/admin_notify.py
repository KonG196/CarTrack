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


def _escape(text: str) -> str:
    """The notes are our own strings, but a user's plate/VIN/station name rides
    inside them — escape so an odd character can never break the HTML letter."""
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _send_admin(
    subject: str,
    heading: str,
    lede: str,
    note: str | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> bool:
    """Render and send one owner note. Returns False when admin mail is off.

    `note` may be multi-line: the plain-text part keeps the newlines, the HTML
    part turns them into <br> so the little spec-sheet blocks (car facts, scan
    results) render on separate lines.
    """
    to = (settings.ADMIN_EMAIL or "").strip()
    if not to:
        return False
    text = f"{heading}\n\n{lede}"
    if note:
        text += f"\n\n{note}"
    html_note = _escape(note).replace("\n", "<br>") if note else None
    return send_mail(
        to,
        subject,
        text,
        html=_render_email(
            lang="uk",
            heading=heading,
            lede=lede,
            button=("Відкрити Kapot", _APP_URL),
            note=html_note,
        ),
        attachments=attachments,
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


def _car_lines(car: Car) -> str:
    """A labelled block describing the car: everything the owner filled in.

    One fact per line so the note reads like a little spec sheet in the mail,
    with blank fields simply omitted rather than showing "None".
    """
    head = " ".join(
        str(part) for part in (car.brand, car.model, car.year) if part
    )
    rows: list[tuple[str, object]] = [
        ("Авто", head),
        ("Покоління", car.generation),
        ("Двигун", car.engine),
        ("Пальне", car.fuel_type),
        ("Пробіг", f"{car.current_odometer:,} км".replace(",", " ")
         if car.current_odometer else None),
        ("VIN", car.vin),
        ("Номер", car.plate),
    ]
    return "\n".join(f"{label}: {value}" for label, value in rows if value)


def notify_first_car(db: Session, user: User, car: Car) -> None:
    """The user added their first car."""
    if user.admin_notified_first_car:
        return
    try:
        user.admin_notified_first_car = True
        db.commit()
        _send_admin(
            subject="Kapot: перша машина",
            heading="Перша машина додана",
            lede=f"{_who(user)} додав(-ла) першу машину.",
            note=_car_lines(car) or None,
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


def _scan_lines(kind: str, fields: dict[str, object] | None) -> str:
    """Human block for the scan: the type plus each recognised field, in order.

    `fields` is an ordered {label: value} of what the OCR read; None/empty
    values are dropped so a partial scan still reads cleanly.
    """
    rows = [("Тип", kind)]
    for label, value in (fields or {}).items():
        rows.append((label, value))
    return "\n".join(f"{label}: {value}" for label, value in rows if value)


def notify_first_ocr(
    db: Session,
    user: User,
    kind: str = "чек",
    fields: dict[str, object] | None = None,
    image: tuple[str, bytes, str] | None = None,
) -> None:
    """The user ran OCR (receipt or work order) for the first time.

    `fields` is the recognised result (label→value) shown in the note; `image`
    is the original photo as (filename, bytes, content_type), attached so the
    owner can eyeball what was scanned against what was read.
    """
    if user.admin_notified_first_ocr:
        return
    try:
        user.admin_notified_first_ocr = True
        db.commit()
        _send_admin(
            subject="Kapot: перше сканування",
            heading="Перше сканування (OCR)",
            lede=f"{_who(user)} вперше скористав(-ла)ся розпізнаванням.",
            note=_scan_lines(kind, fields) or None,
            attachments=[image] if image else None,
        )
    except Exception:  # noqa: BLE001
        logger.exception("admin OCR notification failed for user %s", user.id)
