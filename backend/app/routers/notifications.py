"""In-app notification centre — the proactive nudges, computed on read.

One account-wide endpoint that assembles the same signals the Telegram bot
pushes (due service, consumption spike, seasonal changeover, tyre rotation +
age, expiring ОСЦПВ) for the current user's cars, so the web app surfaces them
too. Read-only; nothing is stored. Dismiss is handled client-side.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.schemas import NotificationList
from app.services.notifications import build_notifications

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=NotificationList)
def list_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationList:
    items = build_notifications(db, current_user)
    return NotificationList(items=items, count=len(items))
