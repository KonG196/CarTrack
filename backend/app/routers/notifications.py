"""In-app notification centre — proactive nudges, computed on read and folded
into a durable history.

The live list is assembled the same way the Telegram bot pushes (due service,
consumption spike, seasonal changeover, tyre rotation + age, expiring ОСЦПВ) for
the current user's cars. Each read also reconciles that computed set into
notification_log, so the history page and the header bell's unread badge survive
after a nudge's condition clears.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import NotificationLog, User
from app.schemas import (
    NotificationHistory,
    NotificationHistoryItem,
    NotificationList,
    UnreadCount,
)
from app.services import notification_log
from app.services.notifications import build_notifications

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=NotificationList)
def list_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationList:
    items = build_notifications(db, current_user)
    # Fold this read into the durable history: new nudges stored, gone ones
    # resolved. Best-effort — a history hiccup must not break the live list.
    try:
        notification_log.reconcile(db, current_user, items)
    except Exception:  # noqa: BLE001
        db.rollback()
    unread = notification_log.unread_count(db, current_user)
    return NotificationList(items=items, count=len(items), unread=unread)


@router.get("/notifications/history", response_model=NotificationHistory)
def notification_history(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationHistory:
    """The full stored log for this user, newest first — active and past."""
    rows = (
        db.execute(
            select(NotificationLog)
            .where(NotificationLog.user_id == current_user.id)
            .order_by(NotificationLog.first_seen_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return NotificationHistory(
        items=[NotificationHistoryItem.model_validate(r) for r in rows],
        unread=notification_log.unread_count(db, current_user),
    )


@router.post("/notifications/read", response_model=UnreadCount)
def mark_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UnreadCount:
    """Mark every unread notification read — called when the centre opens."""
    unread = notification_log.mark_all_read(db, current_user)
    return UnreadCount(unread=unread)
