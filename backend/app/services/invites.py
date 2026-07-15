"""Share links for a car: minting, finding and spending invite tokens.

The token is a 256-bit URL-safe secret that exists in plaintext for exactly
one response. What lands in the database is its bcrypt hash — the same trade
the password reset codes make (services/reset.py): a stolen database yields
no working links, and the price is that a token cannot be looked up by value.

**Why the lookup is a scan.** A bcrypt hash is salted, so `WHERE token_hash =
:hash` cannot work: the only way to match a token to a row is to verify it
against each candidate. The scan is bounded to live invites (unspent and
unexpired), which at this app's scale — a family sharing a car or two — is a
handful of rows. It is O(n) bcrypt verifications per lookup, so a deployment
that ever holds thousands of live invites at once should give tokens a
public lookup key (`<invite_id>.<secret>`, verify only that row's hash)
rather than widen this loop.
"""

from __future__ import annotations

import datetime as dt
import secrets
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_password, verify_password
from app.models import Car, CarInvite, User

#: How long a share link stays usable. Long enough to reach someone who only
#: checks their messages on the weekend, short enough that a link forgotten in
#: a chat history does not stay a way in.
INVITE_TTL_DAYS = 7

#: Where the frontend serves the accept screen (frontend/src/views/JoinCar.jsx).
INVITE_PATH_PREFIX = "/join/"


def generate_invite_token() -> str:
    return secrets.token_urlsafe(32)


def as_utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value


def create_invite(
    db: Session, car: Car, created_by: User, role: str
) -> tuple[CarInvite, str]:
    """Mint a share link for a car, returning the row and the plaintext token.

    The token is the caller's only copy: it is hashed on the way in and can
    never be read back out of the row.
    """
    token = generate_invite_token()
    invite = CarInvite(
        car_id=car.id,
        token_hash=hash_password(token),
        role=role,
        created_by=created_by.id,
        expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=INVITE_TTL_DAYS),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite, token


def is_live(invite: CarInvite, now: Optional[dt.datetime] = None) -> bool:
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)
    if invite.used_at is not None or invite.used_by is not None:
        return False
    return as_utc(invite.expires_at) > now


def find_live_invite(db: Session, token: str) -> Optional[CarInvite]:
    now = dt.datetime.now(dt.timezone.utc)
    candidates = (
        db.execute(
            select(CarInvite)
            .where(
                CarInvite.used_at.is_(None),
                # Naive on purpose: the column stores UTC without an offset,
                # so the bound value must be the same shape on every backend.
                # This only narrows the scan — is_live below is what decides.
                CarInvite.expires_at > now.replace(tzinfo=None),
            )
            .order_by(CarInvite.id)
        )
        .scalars()
        .all()
    )
    for invite in candidates:
        if not is_live(invite, now):
            continue
        if verify_password(token, invite.token_hash):
            return invite
    return None


def spend_invite(db: Session, invite: CarInvite, user: User) -> None:
    """Mark an invite used by this user. Staged only — the caller commits."""
    invite.used_by = user.id
    invite.used_at = dt.datetime.now(dt.timezone.utc)
