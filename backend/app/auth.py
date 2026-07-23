"""Password hashing and JWT authentication helpers."""

from __future__ import annotations

import datetime as dt

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.i18n import t
from app.models import User

ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    # A Google account has no password hash — no password can ever match it, and
    # passlib would raise on a None hash, so reject it cleanly here.
    if not hashed_password:
        return False
    return pwd_context.verify(plain_password, hashed_password)


#: Marks a refresh token so it can never be used as an access token, and an
#: access token can never be spent at /auth/refresh.
REFRESH_PURPOSE = "refresh"


def create_access_token(user_id: int, token_version: int = 0) -> str:
    expire = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": str(user_id), "exp": expire, "tv": token_version}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: int, token_version: int = 0) -> str:
    expire = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "tv": token_version,
        "purpose": REFRESH_PURPOSE,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_refresh_token(token: str) -> tuple[int, int] | None:
    """(user_id, token_version) from a valid refresh token, else None. Rejects
    access tokens and link codes — only a genuine refresh token is accepted."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    if payload.get("purpose") != REFRESH_PURPOSE:
        return None
    try:
        return int(payload["sub"]), int(payload.get("tv", 0))
    except (KeyError, ValueError, TypeError):
        return None


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        # Special-purpose JWTs (e.g. Telegram link codes carry
        # purpose="tg-link") are not access tokens and must not authenticate.
        if payload.get("purpose") is not None:
            raise credentials_exception
        subject = payload.get("sub")
        if subject is None:
            raise credentials_exception
        user_id = int(subject)
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise credentials_exception

    user = db.get(User, user_id)
    if user is None:
        raise credentials_exception
    # A token minted before the last password change/reset is dead. Missing tv
    # (legacy token) reads as 0, matching a fresh account until its first bump.
    if payload.get("tv", 0) != user.token_version:
        raise credentials_exception
    # A blocked account is locked out even with a live token. Blocking bumps
    # token_version so this rarely fires, but a token minted in the same second
    # as the block (same tv) would otherwise slip through — this closes that.
    if user.blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=user.blocked_reason or t("err.accountBlocked", user.language),
        )
    return user


def require_verified_user(current_user: User = Depends(get_current_user)) -> User:
    """Gate the costly external features (OCR scan, plate lookup) behind a
    verified email. Everything else stays open to any signed-in user."""
    if not current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=t("err.verifyEmailForFeature", current_user.language),
        )
    return current_user


def require_superadmin(current_user: User = Depends(get_current_user)) -> User:
    """Gate the owner-only admin panel (/api/admin/*). The flag is set by hand
    on prod, never through signup — see models.User.is_superadmin."""
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin access required",
        )
    return current_user
