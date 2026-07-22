"""Authentication endpoints: register, token, me, password reset via Telegram."""

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.config import settings
from app.database import get_db
from app.i18n import lang_from_accept, t
from app.models import User
from app.ratelimit import RateLimiter, client_ip
from app.schemas import (
    AccountDeleteIn,
    EmailChangeConfirmIn,
    EmailChangeIn,
    EmailChangeOut,
    PasswordChangeIn,
    RefreshIn,
    RegisterOut,
    ResetConfirmIn,
    ResetRequestIn,
    Token,
    UserCreate,
    UserOut,
    UserUpdate,
    VerifyConfirmIn,
    VerifyRequestIn,
)
from app.services.reset import confirm_reset, initiate_reset
from app.services.mailer import mail_enabled
from app.services.verification import (
    confirm_email_change,
    confirm_verification,
    issue_email_change,
    issue_verification,
    verification_required,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

# Sliding windows against credential brute force. Process-local by design
# (single-worker deployment); cleared per test via the conftest fixture.
login_limiter = RateLimiter(limit=5, window_seconds=5 * 60)
register_limiter = RateLimiter(limit=3, window_seconds=60 * 60)
reset_request_limiter = RateLimiter(limit=3, window_seconds=15 * 60)
reset_confirm_limiter = RateLimiter(limit=5, window_seconds=15 * 60)
verify_resend_limiter = RateLimiter(limit=3, window_seconds=15 * 60)
# Password-proof actions on a live session (change password / email / delete
# account): throttle per user so a hijacked session cannot brute the password.
sensitive_limiter = RateLimiter(limit=5, window_seconds=15 * 60)


def _enforce_rate_limit(limiter: RateLimiter, key, lang: str = "en") -> None:
    if not limiter.check(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=t("err.tooManyAttempts", lang),
            headers={"Retry-After": str(limiter.retry_after(key))},
        )


@router.post("/register", response_model=RegisterOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, request: Request, db: Session = Depends(get_db)) -> RegisterOut:
    _enforce_rate_limit(register_limiter, client_ip(request))
    # The account's language comes from the client (the UI the user signed up in);
    # it also localizes this endpoint's own error and the verification email.
    lang = payload.language or lang_from_accept(request.headers.get("accept-language"))
    existing = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=t("auth.email_taken", lang),
        )
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        language=lang,
        currency=payload.currency or "USD",
        # Without a mail server nobody could ever confirm, so the gate stays open.
        email_verified=not verification_required(),
    )
    db.add(user)
    db.flush()
    if verification_required():
        issue_verification(db, user)
    db.commit()
    db.refresh(user)
    return RegisterOut(
        id=user.id,
        email=user.email,
        created_at=user.created_at,
        email_verified=user.email_verified,
        verification_sent=not user.email_verified,
    )


@router.post("/token", response_model=Token)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    email = form_data.username.strip().lower()
    limit_key = (client_ip(request), email)
    _enforce_rate_limit(login_limiter, limit_key)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=t("auth.bad_credentials", lang_from_accept(request.headers.get("accept-language"))),
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Login no longer requires a verified email — anyone with the right password
    # gets in. Verification gates only the costly features (scan, plate lookup)
    # via require_verified_user; see app/auth.py.
    # A legitimate owner should not stay locked out by their earlier typos.
    login_limiter.reset(limit_key)
    return _issue_tokens(user)


def _issue_tokens(user: User) -> Token:
    """A matching access + refresh pair, both bound to the current token_version."""
    return Token(
        access_token=create_access_token(user.id, user.token_version),
        refresh_token=create_refresh_token(user.id, user.token_version),
        token_type="bearer",
    )


@router.post("/refresh", response_model=Token)
def refresh_token(payload: RefreshIn, db: Session = Depends(get_db)) -> Token:
    """Trade a valid refresh token for a fresh access+refresh pair.

    Rejects an access token or link code (wrong purpose), an expired/forged
    token, and — via token_version — one issued before the last password
    change or reset. On any of those the client must log in again.
    """
    decoded = decode_refresh_token(payload.refresh_token)
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if decoded is None:
        raise invalid
    user_id, token_version = decoded
    user = db.get(User, user_id)
    if user is None or token_version != user.token_version:
        raise invalid
    return _issue_tokens(user)


@router.get("/me", response_model=UserOut)
def read_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserOut)
def update_me(
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    updates = payload.model_dump(exclude_unset=True)
    if "display_name" in updates:
        current_user.display_name = updates["display_name"]
    if updates.get("language"):
        current_user.language = updates["language"]
    if updates.get("currency"):
        current_user.currency = updates["currency"]
    for flag in (
        "digest_enabled",
        "reminders_enabled",
        "notify_fuel",
        "notify_seasonal",
        "notify_rotation",
    ):
        if flag in updates:
            setattr(current_user, flag, updates[flag])
    db.commit()
    db.refresh(current_user)
    return current_user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    payload: AccountDeleteIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete the account for good: every owned car, its whole history, and the
    files on disk. Irreversible, so the current password must prove the owner —
    a session left open on a borrowed laptop is not enough (see change_password).

    Files live under ``<UPLOADS_DIR>/<owner_id>/`` (photos and documents both
    keyed on the car's owner), so this user's directory holds exactly the files
    of the cars being deleted. The ORM cascade (User.cars / User.memberships =
    ``all, delete-orphan``) clears the rows; the directory is removed here. Disk
    removal is best-effort — a failed unlink must not strand the row, which is
    the record that actually authorises anything.
    """
    _enforce_rate_limit(sensitive_limiter, current_user.id)
    if not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=t("err.passwordWrong", current_user.language)
        )
    user_uploads = Path(settings.UPLOADS_DIR) / str(current_user.id)
    if user_uploads.exists():
        try:
            shutil.rmtree(user_uploads)
        except OSError as exc:
            logger.error("Failed to wipe uploads for user %s: %s", current_user.id, exc)
    db.delete(current_user)
    db.commit()


@router.post("/password", response_model=Token)
def change_password(
    payload: PasswordChangeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Token:
    """Change the password, proving the current one first, and hand back a fresh
    token pair so the caller stays signed in.

    Being logged in is not proof of being the owner — a session left open on a
    borrowed laptop is enough to be logged in. Knowing the current password is.
    Bumping token_version revokes every OTHER session; the returned pair keeps
    THIS one alive, so the person who just changed their password isn't kicked.
    """
    _enforce_rate_limit(sensitive_limiter, current_user.id)
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=t("err.currentPasswordWrong", current_user.language)
        )
    current_user.hashed_password = hash_password(payload.new_password)
    current_user.token_version += 1
    db.commit()
    db.refresh(current_user)
    return _issue_tokens(current_user)


@router.post("/email", response_model=EmailChangeOut)
def request_email_change(
    payload: EmailChangeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EmailChangeOut:
    """Ask to move the account to another address.

    Nothing changes yet. The address is parked and a code goes to it — only
    someone who can read that inbox can finish the move, and a typo costs a
    retry instead of the account.
    """
    new_email = payload.new_email.strip().lower()
    _enforce_rate_limit(sensitive_limiter, current_user.id)
    if not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=t("err.passwordWrong", current_user.language)
        )
    if new_email == current_user.email.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=t("err.alreadyYourAddress", current_user.language)
        )
    taken = db.execute(
        select(User).where(func.lower(User.email) == new_email, User.id != current_user.id)
    ).scalar_one_or_none()
    if taken is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=t("err.emailTaken", current_user.language)
        )
    if not mail_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=t("err.mailNotConfigured", current_user.language),
        )
    issue_email_change(db, current_user, new_email)
    db.commit()
    return EmailChangeOut(pending_email=new_email)


@router.post("/email/confirm", response_model=UserOut)
def confirm_email(
    payload: EmailChangeConfirmIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    if not confirm_email_change(db, current_user, payload.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=t("err.codeInvalidOrExpired", current_user.language),
        )
    db.refresh(current_user)
    return current_user


@router.post("/reset/request", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(
    payload: ResetRequestIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Start a password reset: always 202 so accounts cannot be enumerated."""
    _enforce_rate_limit(
        reset_request_limiter, (client_ip(request), payload.email.strip().lower())
    )
    await initiate_reset(db, payload.email, payload.channel)
    lang = lang_from_accept(request.headers.get("accept-language"))
    return {"detail": t("msg.resetCodeSentIfExists", lang)}


@router.post("/reset/confirm")
def confirm_password_reset(
    payload: ResetConfirmIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    _enforce_rate_limit(
        reset_confirm_limiter, (client_ip(request), payload.email.strip().lower())
    )
    lang = lang_from_accept(request.headers.get("accept-language"))
    if not confirm_reset(db, payload.email, payload.code, payload.new_password):
        # One message for every failure mode: nothing to learn from probing.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=t("err.codeInvalidOrExpired", lang),
        )
    return {"detail": t("msg.passwordChanged", lang)}


@router.post("/verify/confirm")
def confirm_email(
    payload: VerifyConfirmIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    _enforce_rate_limit(
        reset_confirm_limiter, (client_ip(request), payload.email.strip().lower())
    )
    lang = lang_from_accept(request.headers.get("accept-language"))
    if not confirm_verification(db, payload.email, payload.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=t("err.codeInvalidOrExpired", lang),
        )
    return {"detail": t("msg.emailConfirmed", lang)}


@router.post("/verify/resend", status_code=status.HTTP_202_ACCEPTED)
def resend_verification(
    payload: VerifyRequestIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Always 202: whether the address is registered is not ours to reveal."""
    email = payload.email.strip().lower()
    _enforce_rate_limit(verify_resend_limiter, (client_ip(request), email))
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is not None and not user.email_verified and verification_required():
        issue_verification(db, user)
        db.commit()
    return {"detail": "Якщо акаунт існує і не підтверджений — код надіслано."}
