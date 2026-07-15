"""Transactional one-tap completion of a service interval.

Shared by the REST endpoint (POST /api/intervals/{id}/complete) and the
Telegram reminder «Виконано» button, so both write the exact same history.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from app.models import Car, LogEntry, MaintenanceDetails, ServiceInterval


@dataclass
class IntervalCompletion:

    log: LogEntry
    interval: ServiceInterval
    car: Car


def _to_decimal(value: float) -> Decimal:
    return Decimal(str(value))


def complete_interval(
    db: Session,
    interval: ServiceInterval,
    *,
    odometer: int,
    date: dt.date,
    total_cost: float = 0.0,
    parts_cost: float = 0.0,
    labor_cost: float = 0.0,
    items: Optional[Sequence[str]] = None,
    notes: Optional[str] = None,
    author_id: Optional[int] = None,
) -> IntervalCompletion:
    """Log the maintenance and advance the interval in one transaction.

    Creates a maintenance LogEntry (+MaintenanceDetails) for the interval's
    car, resets the interval to the reported odometer/date and clears its
    reminder stamp, then moves the car's odometer forward (never backwards:
    a completion reported below the current reading still completes, it just
    leaves the car alone). Everything lands in a single commit.

    ``author_id`` signs the entry with whoever ticked the interval off. It is
    optional because an unattributed entry is a valid one (that is what every
    row written before sharing existed is) — not because callers may skip it.
    """
    car = db.get(Car, interval.car_id)
    if car is None:  # pragma: no cover - FK guarantees the car exists
        raise ValueError(f"interval {interval.id} references a missing car")

    log = LogEntry(
        car_id=car.id,
        author_id=author_id,
        type="maintenance",
        odometer=odometer,
        date=date,
        total_cost=_to_decimal(total_cost),
        notes=notes,
    )
    db.add(log)
    db.flush()
    db.add(
        MaintenanceDetails(
            log_entry_id=log.id,
            parts_cost=_to_decimal(parts_cost),
            labor_cost=_to_decimal(labor_cost),
            # An empty item list carries no information: the interval title is
            # what the user actually ticked off.
            items=list(items) if items else [interval.title],
        )
    )

    interval.last_odometer = odometer
    interval.last_date = date
    # The interval is fresh again: the next reminder pass must be free to
    # notify about it without waiting out the old cooldown — or a snooze the
    # owner booked back when it was still due.
    interval.last_notified_at = None
    interval.snoozed_until = None

    if odometer > car.current_odometer:
        car.current_odometer = odometer

    db.commit()
    db.refresh(log)
    db.refresh(interval)
    db.refresh(car)
    return IntervalCompletion(log=log, interval=interval, car=car)
