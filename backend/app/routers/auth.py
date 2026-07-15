"""Authentication endpoints: register, token, me, password reset via Telegram."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.database import get_db
from app.models import User
from app.ratelimit import RateLimiter, client_ip
from app.schemas import (
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
from app.services.verification import (
    confirm_verification,
    issue_verification,
    verification_required,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Sliding windows against credential brute force. Process-local by design
# (single-worker deployment); cleared per test via the conftest fixture.
login_limiter = RateLimiter(limit=5, window_seconds=5 * 60)
register_limiter = RateLimiter(limit=3, window_seconds=60 * 60)
reset_request_limiter = RateLimiter(limit=3, window_seconds=15 * 60)
reset_confirm_limiter = RateLimiter(limit=5, window_seconds=15 * 60)
verify_resend_limiter = RateLimiter(limit=3, window_seconds=15 * 60)


def _enforce_rate_limit(limiter: RateLimiter, key) -> None:
    if not limiter.check(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Забагато спроб. Спробуйте пізніше.",
            headers={"Retry-After": str(limiter.retry_after(key))},
        )


@router.post("/register", response_model=RegisterOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, request: Request, db: Session = Depends(get_db)) -> RegisterOut:
    _enforce_rate_limit(register_limiter, client_ip(request))
    existing = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
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
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Підтвердіть пошту — ми надіслали код на вашу адресу.",
        )
    # A legitimate owner should not stay locked out by their earlier typos.
    login_limiter.reset(limit_key)
    return Token(access_token=create_access_token(user.id), token_type="bearer")


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
    db.commit()
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
    return {"detail": "Якщо акаунт існує — ми надіслали код."}


@router.post("/reset/confirm")
def confirm_password_reset(
    payload: ResetConfirmIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    _enforce_rate_limit(
        reset_confirm_limiter, (client_ip(request), payload.email.strip().lower())
    )
    if not confirm_reset(db, payload.email, payload.code, payload.new_password):
        # One message for every failure mode: nothing to learn from probing.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Невірний або прострочений код",
        )
    return {"detail": "Пароль змінено"}


@router.post("/verify/confirm")
def confirm_email(
    payload: VerifyConfirmIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    _enforce_rate_limit(
        reset_confirm_limiter, (client_ip(request), payload.email.strip().lower())
    )
    if not confirm_verification(db, payload.email, payload.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Невірний або прострочений код",
        )
    return {"detail": "Пошту підтверджено"}


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
