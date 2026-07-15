"""Telegram account-linking endpoints and link-code JWT helpers."""

from __future__ import annotations

import datetime as dt

import jwt
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth import ALGORITHM, get_current_user
from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import TelegramLinkCodeResponse, TelegramStatus

router = APIRouter(prefix="/telegram", tags=["telegram"])

LINK_CODE_PURPOSE = "tg-link"


class InvalidLinkCodeError(Exception):
    """Raised when a Telegram link code is malformed, expired or misused."""


def create_link_code(user_id: int) -> str:
    expire = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
        minutes=settings.LINK_CODE_EXPIRE_MINUTES
    )
    payload = {"sub": str(user_id), "purpose": LINK_CODE_PURPOSE, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_link_code(code: str) -> int:
    try:
        payload = jwt.decode(code, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError as exc:
        raise InvalidLinkCodeError("invalid or expired link code") from exc
    if payload.get("purpose") != LINK_CODE_PURPOSE:
        raise InvalidLinkCodeError("not a telegram link code")
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidLinkCodeError("invalid link code subject") from exc


@router.post("/link-code", response_model=TelegramLinkCodeResponse)
def create_telegram_link_code(
    current_user: User = Depends(get_current_user),
) -> TelegramLinkCodeResponse:
    code = create_link_code(current_user.id)
    deep_link = (
        f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={code}"
        if settings.TELEGRAM_BOT_USERNAME
        else None
    )
    return TelegramLinkCodeResponse(
        code=code,
        deep_link=deep_link,
        expires_in_minutes=settings.LINK_CODE_EXPIRE_MINUTES,
    )


@router.get("/status", response_model=TelegramStatus)
def telegram_status(current_user: User = Depends(get_current_user)) -> TelegramStatus:
    return TelegramStatus(linked=current_user.telegram_chat_id is not None)


@router.delete("/link", status_code=status.HTTP_204_NO_CONTENT)
def unlink_telegram(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    current_user.telegram_chat_id = None
    db.commit()
    return None
