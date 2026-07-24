"""Reconcile computed nudges into the persisted notification history.

The live notifications are computed on read (services/notifications). This module
folds each read into `notification_log` so history is durable: new keys are
inserted, still-present keys refresh `last_active_at` (and un-resolve if they had
lapsed and returned), and keys no longer present are marked resolved. The stored
title/body/etc. are the FIRST-seen snapshot, so old rows read correctly even
though the live copy would now differ.

Cheap by construction: a handful of rows per user, folded into the request that
already computed the live list — no extra query fan-out, no polling.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import NotificationLog, User


def reconcile(db: Session, user: User, active_items: list[dict]) -> None:
    """Sync the computed `active_items` into notification_log for `user`."""
    now = dt.datetime.utcnow()
    active_by_key = {item["id"]: item for item in active_items}

    existing = (
        db.execute(
            select(NotificationLog).where(NotificationLog.user_id == user.id)
        )
        .scalars()
        .all()
    )
    existing_by_key = {row.notif_key: row for row in existing}

    # Insert brand-new nudges; refresh the ones still active.
    for key, item in active_by_key.items():
        row = existing_by_key.get(key)
        if row is None:
            db.add(
                NotificationLog(
                    user_id=user.id,
                    notif_key=key,
                    kind=item.get("kind", ""),
                    severity=item.get("severity", "info"),
                    car_id=item.get("car_id"),
                    car_label=item.get("car_label"),
                    title=item.get("title", ""),
                    body=item.get("body", ""),
                    action=item.get("action"),
                    first_seen_at=now,
                    last_active_at=now,
                )
            )
        else:
            row.last_active_at = now
            # A nudge that lapsed and came back (same key) is active again.
            row.resolved_at = None

    # Mark rows no longer computed as resolved (only the ones still marked active).
    for row in existing:
        if row.notif_key not in active_by_key and row.resolved_at is None:
            row.resolved_at = now

    db.commit()


def unread_count(db: Session, user: User) -> int:
    """How many stored notifications the user hasn't opened the centre for yet.

    Only counts rows that are still active — a nudge that resolved before the
    user ever looked shouldn't keep the badge lit."""
    return (
        db.scalar(
            select(func.count(NotificationLog.id)).where(
                NotificationLog.user_id == user.id,
                NotificationLog.read_at.is_(None),
                NotificationLog.resolved_at.is_(None),
            )
        )
        or 0
    )


def mark_all_read(db: Session, user: User) -> int:
    """Mark every unread row read (the user opened the centre). Returns the new
    unread count (0)."""
    db.execute(
        update(NotificationLog)
        .where(
            NotificationLog.user_id == user.id,
            NotificationLog.read_at.is_(None),
        )
        .values(read_at=dt.datetime.utcnow())
    )
    db.commit()
    return 0
