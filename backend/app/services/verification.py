"""Email verification codes.

Same shape as the Telegram reset codes: a short numeric code the user can
retype, stored only as a bcrypt hash with an expiry, single-use.
"""

from __future__ import annotations

import datetime as dt
import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import hash_password, verify_password
from app.config import settings
from app.models import User
from app.services.mailer import mail_enabled, send_verification

CODE_DIGITS = 6


def _new_code() -> str:
    return f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"


def issue_verification(db: Session, user: User) -> str | None:
    """Stamp a fresh code on the user and mail it.

    Returns the plain code when mail is off (so tests and local development can
    read it); None once it has actually been sent, because nothing outside the
    letter is allowed to know it.
    """
    code = _new_code()
    user.verify_code_hash = hash_password(code)
    user.verify_code_expires_at = dt.datetime.utcnow() + dt.timedelta(
        hours=settings.VERIFY_CODE_EXPIRE_HOURS
    )
    db.flush()
    sent = send_verification(user.email, code)
    return None if sent else code


def confirm_verification(db: Session, email: str, code: str) -> bool:
    user = db.execute(
        select(User).where(func.lower(User.email) == email.strip().lower())
    ).scalar_one_or_none()
    if user is None:
        return False
    if user.email_verified:
        # Re-confirming an already verified address is a no-op success: users
        # click the link twice and must not see an error for it.
        return True
    if user.verify_code_hash is None or user.verify_code_expires_at is None:
        return False
    if user.verify_code_expires_at < dt.datetime.utcnow():
        return False
    if not verify_password(code, user.verify_code_hash):
        return False

    user.email_verified = True
    user.verify_code_hash = None
    user.verify_code_expires_at = None
    db.commit()
    return True


def verification_required() -> bool:
    """Without a mail server the gate would lock every new account out."""
    return mail_enabled()
