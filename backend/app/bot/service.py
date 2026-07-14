"""Synchronous database operations behind the Telegram bot handlers.

The bot talks to the database directly (no HTTP round-trips to the API);
every function takes an explicit Session so handlers control the lifetime
and tests can supply their own engine.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Car, LogEntry, ServiceInterval, User
from app.routers.telegram import InvalidLinkCodeError, decode_link_code
from app.services.intervals import compute_avg_daily_km, compute_interval_status

NOTIFY_COOLDOWN_DAYS = 7


@dataclass
class OdometerUpdate:
    """Result of a forward-only odometer update attempt."""

    car: Car
    old_odometer: int
    new_odometer: int
    updated: bool
    top_intervals: list[tuple[ServiceInterval, dict]]


@dataclass
class ReminderItem:
    """A due interval scheduled for the aggregated reminder message."""

    car: Car
    interval: ServiceInterval
    computed: dict


# ---------------------------------------------------------------------------
# Linking
# ---------------------------------------------------------------------------


def link_user_by_code(db: Session, code: str, chat_id: str) -> User:
    """Link a Telegram chat to the user encoded in the link code.

    Chat ids are unique across users by app logic: a chat already linked to
    another user is re-linked, clearing the old user's link first.
    """
    user_id = decode_link_code(code)
    user = db.get(User, user_id)
    if user is None:
        raise InvalidLinkCodeError("link code references an unknown user")
    previous = db.execute(
        select(User).where(User.telegram_chat_id == chat_id, User.id != user.id)
    ).scalar_one_or_none()
    if previous is not None:
        previous.telegram_chat_id = None
    user.telegram_chat_id = chat_id
    db.commit()
    return user


def unlink_chat(db: Session, chat_id: str) -> bool:
    """Remove the link for a chat id; returns True when a link existed."""
    user = get_user_by_chat(db, chat_id)
    if user is None:
        return False
    user.telegram_chat_id = None
    db.commit()
    return True


def get_user_by_chat(db: Session, chat_id: str) -> Optional[User]:
    """Resolve a Telegram chat id to the linked user, if any."""
    return db.execute(
        select(User).where(User.telegram_chat_id == chat_id)
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Cars, odometer, quick expenses
# ---------------------------------------------------------------------------


def list_cars(db: Session, user: User) -> list[Car]:
    """The user's cars ordered by id."""
    return list(
        db.execute(select(Car).where(Car.user_id == user.id).order_by(Car.id))
        .scalars()
        .all()
    )


def get_car(db: Session, user: User, car_id: int) -> Optional[Car]:
    """Fetch one of the user's cars by id (ownership enforced)."""
    return db.execute(
        select(Car).where(Car.id == car_id, Car.user_id == user.id)
    ).scalar_one_or_none()


def _car_avg_daily_km(db: Session, car: Car) -> float:
    logs = db.execute(select(LogEntry).where(LogEntry.car_id == car.id)).scalars().all()
    return compute_avg_daily_km(logs)


def car_interval_statuses(
    db: Session, car: Car, today: dt.date | None = None
) -> list[tuple[ServiceInterval, dict]]:
    """Compute the status of every interval of a car, nearest first."""
    avg_daily_km = _car_avg_daily_km(db, car)
    intervals = (
        db.execute(
            select(ServiceInterval)
            .where(ServiceInterval.car_id == car.id)
            .order_by(ServiceInterval.id)
        )
        .scalars()
        .all()
    )
    statuses = [
        (
            interval,
            compute_interval_status(
                interval=interval,
                current_odometer=car.current_odometer,
                avg_daily_km=avg_daily_km,
                today=today,
            ),
        )
        for interval in intervals
    ]
    statuses.sort(key=lambda pair: pair[1]["health_pct"])
    return statuses


def update_odometer(db: Session, car_id: int, value: int) -> Optional[OdometerUpdate]:
    """Forward-only odometer update.

    Returns None for an unknown car. A value below the current odometer is
    refused (updated=False, odometer untouched); otherwise the car moves
    forward and the refreshed top-3 nearest intervals are included.
    """
    car = db.get(Car, car_id)
    if car is None:
        return None
    old_odometer = car.current_odometer
    if value < old_odometer:
        return OdometerUpdate(
            car=car,
            old_odometer=old_odometer,
            new_odometer=old_odometer,
            updated=False,
            top_intervals=[],
        )
    car.current_odometer = value
    db.commit()
    db.refresh(car)
    return OdometerUpdate(
        car=car,
        old_odometer=old_odometer,
        new_odometer=value,
        updated=True,
        top_intervals=car_interval_statuses(db, car)[:3],
    )


def create_quick_expense(
    db: Session, car_id: int, title: str, amount: float
) -> Optional[LogEntry]:
    """Create an expense log entry dated today at the car's current odometer."""
    car = db.get(Car, car_id)
    if car is None:
        return None
    log = LogEntry(
        car_id=car.id,
        type="expense",
        odometer=car.current_odometer,
        date=dt.date.today(),
        total_cost=Decimal(str(round(amount, 2))),
        notes=title,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


# ---------------------------------------------------------------------------
# Ukrainian summaries
# ---------------------------------------------------------------------------


def format_interval_line(interval: ServiceInterval, computed: dict) -> str:
    """One human-readable Ukrainian line about an interval's health."""
    remaining: list[str] = []
    km_left = computed["km_left"]
    days_left = computed["days_left"]
    if km_left is not None:
        remaining.append(
            f"залишилось {km_left} км" if km_left >= 0 else f"прострочено на {-km_left} км"
        )
    if days_left is not None:
        remaining.append(
            f"залишилось {days_left} дн."
            if days_left >= 0
            else f"прострочено на {-days_left} дн."
        )
    detail = ", ".join(remaining) if remaining else "без прив'язки до пробігу чи дати"
    return f"- {interval.title}: {computed['health_pct']:.0f}% ({detail})"


def status_summary(db: Session, user: User, today: dt.date | None = None) -> str:
    """Build the Ukrainian /status text for all of the user's cars."""
    cars = list_cars(db, user)
    if not cars:
        return "У гаражі поки немає авто. Додайте перше авто у веб-додатку Kapot Tracker."
    blocks: list[str] = []
    for car in cars:
        lines = [f"{car.brand} {car.model} — пробіг {car.current_odometer} км"]
        statuses = car_interval_statuses(db, car, today=today)[:3]
        if statuses:
            lines.extend(format_interval_line(interval, computed) for interval, computed in statuses)
        else:
            lines.append("- Інтервали ТО не налаштовані.")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------


def reminder_targets(
    db: Session, today: dt.date | None = None
) -> list[tuple[User, list[ReminderItem]]]:
    """Linked users with due intervals that were not notified recently.

    An interval qualifies when its status is due_soon or overdue and
    last_notified_at is NULL or at least NOTIFY_COOLDOWN_DAYS days old.
    Items are grouped per user, in car order.
    """
    if today is None:
        today = dt.date.today()
    cutoff = today - dt.timedelta(days=NOTIFY_COOLDOWN_DAYS)
    users = (
        db.execute(
            select(User).where(User.telegram_chat_id.is_not(None)).order_by(User.id)
        )
        .scalars()
        .all()
    )
    targets: list[tuple[User, list[ReminderItem]]] = []
    for user in users:
        items: list[ReminderItem] = []
        for car in list_cars(db, user):
            for interval, computed in car_interval_statuses(db, car, today=today):
                if computed["status"] not in ("due_soon", "overdue"):
                    continue
                if interval.last_notified_at is not None and interval.last_notified_at > cutoff:
                    continue
                items.append(ReminderItem(car=car, interval=interval, computed=computed))
        if items:
            targets.append((user, items))
    return targets


def stamp_notified(
    db: Session, interval_ids: list[int], today: dt.date | None = None
) -> None:
    """Stamp last_notified_at on the given intervals."""
    if not interval_ids:
        return
    if today is None:
        today = dt.date.today()
    intervals = (
        db.execute(select(ServiceInterval).where(ServiceInterval.id.in_(interval_ids)))
        .scalars()
        .all()
    )
    for interval in intervals:
        interval.last_notified_at = today
    db.commit()


def latest_log_date(db: Session, user: User) -> Optional[dt.date]:
    """The date of the user's most recent log entry across all cars."""
    return db.execute(
        select(func.max(LogEntry.date))
        .join(Car, LogEntry.car_id == Car.id)
        .where(Car.user_id == user.id)
    ).scalar_one_or_none()
