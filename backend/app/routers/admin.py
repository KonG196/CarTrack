"""Superadmin panel — user management only (v1).

Every endpoint is gated by `require_superadmin`. Every mutation writes exactly
one admin_audit_log row in the SAME transaction as the change, so the trail can
never disagree with what happened. Three things the superadmin may never do to
their own account — block, demote, delete — are refused server-side (400), so a
slip in the UI can't lock the owner out of their own panel.

Passwords are never edited here. The only way to a new password is a reset link
(generated or mailed), because the stored value is a hash, not a secret we hold.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import hash_password, require_superadmin
from app.database import get_db
from app.models import AdminAuditLog, Car, LogEntry, User
from app.schemas import (
    AdminAuditRow,
    AdminLinkOut,
    AdminStatusUpdate,
    AdminUserDetail,
    AdminUserList,
    AdminUserRow,
    AdminUserUpdate,
)
from app.services import audit
from app.services.accounts import purge_account
from app.services.mailer import (
    reset_link,
    send_reset_code_mail,
    send_verification,
    verify_link,
)
from app.services.reset import RESET_CODE_TTL_MINUTES, generate_reset_code
from app.services.verification import issue_verification_code

router = APIRouter(prefix="/admin", tags=["admin"])


def _row(db: Session, user: User) -> AdminUserRow:
    """A list/detail row with the two cheap counts filled in."""
    car_count = db.scalar(
        select(func.count(Car.id)).where(Car.user_id == user.id)
    )
    log_count = db.scalar(
        select(func.count(LogEntry.id))
        .join(Car, LogEntry.car_id == Car.id)
        .where(Car.user_id == user.id)
    )
    row = AdminUserRow.model_validate(user)
    row.car_count = car_count or 0
    row.log_count = log_count or 0
    return row


def _get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _forbid_self(actor: User, target: User, what: str) -> None:
    """The three actions a superadmin must not aim at themselves."""
    if actor.id == target.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You cannot {what} your own account.",
        )


@router.get("/users", response_model=AdminUserList)
def list_users(
    q: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_superadmin),
) -> AdminUserList:
    """Users newest-first, optionally filtered by an email/name substring."""
    query = select(User)
    count_query = select(func.count(User.id))
    if q:
        needle = f"%{q.strip().lower()}%"
        clause = func.lower(User.email).like(needle) | func.lower(
            func.coalesce(User.display_name, "")
        ).like(needle)
        query = query.where(clause)
        count_query = count_query.where(clause)
    total = db.scalar(count_query) or 0
    users = (
        db.execute(
            query.order_by(User.created_at.desc()).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return AdminUserList(users=[_row(db, u) for u in users], total=total)


@router.get("/users/{user_id}", response_model=AdminUserDetail)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_superadmin),
) -> AdminUserDetail:
    user = _get_user(db, user_id)
    cars = (
        db.execute(select(Car).where(Car.user_id == user.id).order_by(Car.created_at))
        .scalars()
        .all()
    )
    audit_rows = (
        db.execute(
            select(AdminAuditLog)
            .where(AdminAuditLog.target_user_id == user.id)
            .order_by(AdminAuditLog.created_at.desc())
            .limit(50)
        )
        .scalars()
        .all()
    )
    return AdminUserDetail(
        user=_row(db, user),
        cars=cars,
        audit=[AdminAuditRow.model_validate(r) for r in audit_rows],
    )


@router.patch("/users/{user_id}", response_model=AdminUserDetail)
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin),
) -> AdminUserDetail:
    """Edit identity/preferences. Email must stay unique; a hashed password is
    never touched here."""
    user = _get_user(db, user_id)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to update"
        )
    new_email = updates.get("email")
    if new_email and new_email != user.email:
        taken = db.execute(
            select(User).where(User.email == new_email, User.id != user.id)
        ).scalar_one_or_none()
        if taken is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="That address is already taken",
            )
    changed: dict[str, object] = {}
    for field, value in updates.items():
        if getattr(user, field) != value:
            changed[field] = value
            setattr(user, field, value)
    if changed:
        audit.record(db, actor=admin, action="edit_user", target=user, detail=changed)
    db.commit()
    db.refresh(user)
    return get_user(user_id, db, admin)


@router.post("/users/{user_id}/status", response_model=AdminUserDetail)
def set_status(
    user_id: int,
    payload: AdminStatusUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin),
) -> AdminUserDetail:
    """Flip email_verified / is_superadmin / blocked. Blocking severs the
    target's live sessions (token_version bump) and needs a reason; a superadmin
    cannot block or demote themselves."""
    user = _get_user(db, user_id)
    fields = payload.model_dump(exclude_unset=True)

    if "email_verified" in fields and fields["email_verified"] != user.email_verified:
        user.email_verified = fields["email_verified"]
        audit.record(
            db,
            actor=admin,
            action="verify" if user.email_verified else "unverify",
            target=user,
        )

    if "is_superadmin" in fields and fields["is_superadmin"] != user.is_superadmin:
        if not fields["is_superadmin"]:
            _forbid_self(admin, user, "demote")
        user.is_superadmin = fields["is_superadmin"]
        audit.record(
            db,
            actor=admin,
            action="set_superadmin" if user.is_superadmin else "unset_superadmin",
            target=user,
        )

    if "blocked" in fields and fields["blocked"] != user.blocked:
        if fields["blocked"]:
            _forbid_self(admin, user, "block")
            reason = (payload.blocked_reason or "").strip()
            if not reason:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A block reason is required.",
                )
            user.blocked = True
            user.blocked_reason = reason
            # Sever every live session of the blocked account at once.
            user.token_version += 1
            audit.record(
                db, actor=admin, action="block", target=user, detail={"reason": reason}
            )
        else:
            user.blocked = False
            user.blocked_reason = None
            audit.record(db, actor=admin, action="unblock", target=user)

    db.commit()
    db.refresh(user)
    return get_user(user_id, db, admin)


def _mint_reset_code(user: User) -> str:
    """Stamp a fresh reset code on the user and return it (the caller builds the
    link and/or mails it). Mirrors services.reset.initiate_reset's DB half, but
    hands the code back instead of only delivering it — the panel shows/copies
    the link."""
    code = generate_reset_code()
    user.reset_code_hash = hash_password(code)
    user.reset_code_expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
        minutes=RESET_CODE_TTL_MINUTES
    )
    user.reset_code_attempts = 0
    return code


@router.post("/users/{user_id}/reset-link", response_model=AdminLinkOut)
def reset_link_endpoint(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin),
) -> AdminLinkOut:
    user = _get_user(db, user_id)
    link = reset_link(user.email, _mint_reset_code(user))
    audit.record(db, actor=admin, action="issue_reset_link", target=user)
    db.commit()
    return AdminLinkOut(link=link, emailed=False)


@router.post("/users/{user_id}/verify-link", response_model=AdminLinkOut)
def verify_link_endpoint(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin),
) -> AdminLinkOut:
    user = _get_user(db, user_id)
    link = verify_link(user.email, issue_verification_code(db, user))
    audit.record(db, actor=admin, action="issue_verify_link", target=user)
    db.commit()
    return AdminLinkOut(link=link, emailed=False)


@router.post("/users/{user_id}/send-reset", response_model=AdminLinkOut)
def send_reset_endpoint(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin),
) -> AdminLinkOut:
    """Mail the reset link to the user. The link is generated the same way and
    also returned, so the panel can still show it."""
    user = _get_user(db, user_id)
    code = _mint_reset_code(user)
    emailed = send_reset_code_mail(user.email, code, user.language)
    audit.record(
        db, actor=admin, action="send_reset", target=user, detail={"emailed": emailed}
    )
    db.commit()
    return AdminLinkOut(link=reset_link(user.email, code), emailed=emailed)


@router.post("/users/{user_id}/send-verify", response_model=AdminLinkOut)
def send_verify_endpoint(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin),
) -> AdminLinkOut:
    """Mail the verification link to the user, returning it as well."""
    user = _get_user(db, user_id)
    code = issue_verification_code(db, user)
    link = verify_link(user.email, code)
    emailed = send_verification(user.email, code, user.language)
    audit.record(
        db, actor=admin, action="send_verify", target=user, detail={"emailed": emailed}
    )
    db.commit()
    return AdminLinkOut(link=link, emailed=emailed)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_superadmin),
) -> None:
    """Delete an account and everything that belongs only to it. A superadmin
    cannot delete their own account here (use the normal account-delete flow,
    which asks for the password)."""
    user = _get_user(db, user_id)
    _forbid_self(admin, user, "delete")
    # Audit BEFORE the delete so the target's email is captured while it exists;
    # target goes to NULL on delete, target_email keeps the record readable.
    audit.record(
        db,
        actor=admin,
        action="delete_user",
        target=user,
        detail={"email": user.email},
    )
    purge_account(db, user)
    db.commit()


@router.get("/audit", response_model=list[AdminAuditRow])
def audit_feed(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_superadmin),
) -> list[AdminAuditRow]:
    rows = (
        db.execute(
            select(AdminAuditLog)
            .order_by(AdminAuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return [AdminAuditRow.model_validate(r) for r in rows]
