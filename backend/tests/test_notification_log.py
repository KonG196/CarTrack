"""Persisted notification history: reconcile computed nudges into the log, drive
the unread badge, resolve nudges that drop out, and mark-all-read."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import NotificationLog, User
from app.services import notification_log


def _user(sf: sessionmaker) -> User:
    with sf() as db:
        u = User(email="n@example.com", hashed_password="x")
        db.add(u)
        db.commit()
        db.refresh(u)
        db.expunge(u)
        return u


def _item(key: str, **over) -> dict:
    return {
        "id": key,
        "kind": over.get("kind", "interval"),
        "severity": over.get("severity", "warn"),
        "car_id": over.get("car_id", 1),
        "car_label": over.get("car_label", "Test Car"),
        "title": over.get("title", "Service due"),
        "body": over.get("body", "500 km left"),
        "action": over.get("action", "/intervals"),
    }


def test_reconcile_inserts_new_and_counts_unread(db_session_factory) -> None:
    user = _user(db_session_factory)
    with db_session_factory() as db:
        user = db.merge(user)
        notification_log.reconcile(db, user, [_item("interval:1:due"), _item("spike:9")])
        assert notification_log.unread_count(db, user) == 2
        rows = db.execute(
            select(NotificationLog).where(NotificationLog.user_id == user.id)
        ).scalars().all()
        assert {r.notif_key for r in rows} == {"interval:1:due", "spike:9"}
        assert all(r.read_at is None and r.resolved_at is None for r in rows)


def test_reconcile_is_idempotent(db_session_factory) -> None:
    """The same nudge on a second read must not create a duplicate row."""
    user = _user(db_session_factory)
    with db_session_factory() as db:
        user = db.merge(user)
        notification_log.reconcile(db, user, [_item("interval:1:due")])
        notification_log.reconcile(db, user, [_item("interval:1:due")])
        rows = db.execute(
            select(NotificationLog).where(NotificationLog.user_id == user.id)
        ).scalars().all()
        assert len(rows) == 1


def test_dropped_nudge_is_resolved(db_session_factory) -> None:
    user = _user(db_session_factory)
    with db_session_factory() as db:
        user = db.merge(user)
        notification_log.reconcile(db, user, [_item("interval:1:due")])
        # Next read: the nudge is gone (service logged) → resolved, badge clears.
        notification_log.reconcile(db, user, [])
        row = db.execute(
            select(NotificationLog).where(NotificationLog.user_id == user.id)
        ).scalar_one()
        assert row.resolved_at is not None
        assert notification_log.unread_count(db, user) == 0  # resolved ≠ unread


def test_returning_nudge_unresolves(db_session_factory) -> None:
    user = _user(db_session_factory)
    with db_session_factory() as db:
        user = db.merge(user)
        notification_log.reconcile(db, user, [_item("seasonal:1")])
        notification_log.reconcile(db, user, [])  # lapses
        notification_log.reconcile(db, user, [_item("seasonal:1")])  # comes back
        row = db.execute(
            select(NotificationLog).where(NotificationLog.user_id == user.id)
        ).scalar_one()
        assert row.resolved_at is None


def test_mark_all_read_clears_badge(db_session_factory) -> None:
    user = _user(db_session_factory)
    with db_session_factory() as db:
        user = db.merge(user)
        notification_log.reconcile(db, user, [_item("interval:1:due"), _item("spike:9")])
        assert notification_log.unread_count(db, user) == 2
        assert notification_log.mark_all_read(db, user) == 0
        assert notification_log.unread_count(db, user) == 0
        # A NEW nudge after reading is unread again.
        notification_log.reconcile(db, user, [_item("interval:1:due"), _item("spike:9"), _item("rotation:3")])
        assert notification_log.unread_count(db, user) == 1


def test_snapshot_preserved_after_resolve(db_session_factory) -> None:
    """History keeps the first-seen copy even after the nudge is gone."""
    user = _user(db_session_factory)
    with db_session_factory() as db:
        user = db.merge(user)
        notification_log.reconcile(
            db, user, [_item("interval:1:due", title="Oil change", body="due now")]
        )
        notification_log.reconcile(db, user, [])
        row = db.execute(
            select(NotificationLog).where(NotificationLog.user_id == user.id)
        ).scalar_one()
        assert row.title == "Oil change" and row.body == "due now"
