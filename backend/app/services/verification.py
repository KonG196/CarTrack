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
from app.services.admin_notify import notify_first_verified
from app.services.mailer import mail_enabled, send_email_change, send_verification

CODE_DIGITS = 6
#: Wrong guesses before the verify code/token is burned (per-account, IP-independent).
_MAX_VERIFY_ATTEMPTS = 5


def _new_code() -> str:
    # Short numeric code the user retypes — used by the email-change flow, where
    # the confirmation is a manual entry, not a link.
    return f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"


def _new_token() -> str:
    # Long, unguessable token for registration verification: that email carries
    # only a link (no code to retype), so the value must not be brute-forceable.
    # 32 random bytes → ~43 url-safe chars, ~256 bits of entropy.
    return secrets.token_urlsafe(32)


def issue_verification_code(db: Session, user: User) -> str:
    """Stamp a fresh verification token on the user and return it, without
    sending anything. The caller decides what to do with the token (build a
    link, mail it, both) — used by the admin panel's link generation and by
    issue_verification below."""
    code = _new_token()
    user.verify_code_hash = hash_password(code)
    user.verify_code_expires_at = dt.datetime.utcnow() + dt.timedelta(
        hours=settings.VERIFY_CODE_EXPIRE_HOURS
    )
    user.verify_code_attempts = 0  # fresh code, fresh attempt budget
    db.flush()
    return code


def issue_verification(db: Session, user: User) -> str | None:
    """Stamp a fresh code on the user and mail it.

    Returns the plain token when mail is off (so tests and local development can
    read it); None once it has actually been sent, because nothing outside the
    letter is allowed to know it.
    """
    code = issue_verification_code(db, user)
    sent = send_verification(user.email, code, user.language)
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
        # Burn the code after a few misses so it cannot be brute forced.
        user.verify_code_attempts += 1
        if user.verify_code_attempts >= _MAX_VERIFY_ATTEMPTS:
            user.verify_code_hash = None
            user.verify_code_expires_at = None
        db.commit()
        return False

    user.email_verified = True
    user.verify_code_hash = None
    user.verify_code_expires_at = None
    user.verify_code_attempts = 0
    db.commit()
    notify_first_verified(db, user)
    return True


def verification_required() -> bool:
    """Without a mail server the gate would lock every new account out."""
    return mail_enabled()


def issue_email_change(db: Session, user: User, new_email: str) -> str | None:
    """Park a new address and mail a code to it.

    The address is not written to `user.email` here, and that is the point:
    login is gated on a verified address, so an unconfirmed one in that column
    would lock the user out of the account over a typo, with no way back.
    """
    user.pending_email = new_email.strip().lower()
    code = _new_code()
    user.verify_code_hash = hash_password(code)
    user.verify_code_expires_at = dt.datetime.utcnow() + dt.timedelta(
        hours=settings.VERIFY_CODE_EXPIRE_HOURS
    )
    user.verify_code_attempts = 0  # fresh code, fresh attempt budget
    db.flush()
    sent = send_email_change(user.pending_email, code, user.language)
    return None if sent else code


def confirm_email_change(db: Session, user: User, code: str) -> bool:
    """Move the account to the parked address, if the code came back."""
    if not user.pending_email:
        return False
    if user.verify_code_hash is None or user.verify_code_expires_at is None:
        return False
    if user.verify_code_expires_at < dt.datetime.utcnow():
        return False
    if not verify_password(code, user.verify_code_hash):
        return False
    # Someone else may have registered the address while the code was in the
    # inbox. Unique on the column would raise here anyway; this says why.
    taken = db.execute(
        select(User).where(
            func.lower(User.email) == user.pending_email, User.id != user.id
        )
    ).scalar_one_or_none()
    if taken is not None:
        return False

    user.email = user.pending_email
    user.pending_email = None
    user.email_verified = True
    user.verify_code_hash = None
    user.verify_code_expires_at = None
    db.commit()
    return True
