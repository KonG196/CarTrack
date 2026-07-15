"""Service interval status and prediction engine."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from app.models import Car, LogEntry, ServiceInterval

DEFAULT_AVG_DAILY_KM = 40.0

# How far back to look for the car's current pace, widest window last. A car
# is not driven the same way for its whole life — the owner's Golf averaged
# 66 km/day since 2016, yet the German years and the Ukrainian ones differ by
# a factor of two, and every ТО forecast is built on this one number. So the
# recent window wins, and only a window too thin to mean anything widens.
AVG_WINDOW_DAYS: tuple[int, ...] = (90, 180, 365)

# Under a week of history describes a particular week, not a pace: a single
# 300 km weekend would otherwise read as 100 km/day forever.
MIN_WINDOW_SPAN_DAYS = 7


def _pace(logs: Sequence[LogEntry], min_span_days: int) -> float | None:
    """Daily km across a set of logs, or None when they cannot say.

    Spans the extremes rather than the first and last row: one mistyped
    odometer would otherwise make the delta negative and throw away an
    otherwise usable window.
    """
    if len(logs) < 2:
        return None

    dates = [log.date for log in logs]
    odometers = [log.odometer for log in logs]
    day_span = (max(dates) - min(dates)).days
    odometer_delta = max(odometers) - min(odometers)

    if day_span < min_span_days or odometer_delta <= 0:
        return None
    return odometer_delta / day_span


def compute_avg_daily_km(
    logs: Sequence[LogEntry], today: dt.date | None = None
) -> float:
    if today is None:
        today = dt.date.today()

    for window_days in AVG_WINDOW_DAYS:
        cutoff = today - dt.timedelta(days=window_days)
        recent = [log for log in logs if log.date >= cutoff]
        pace = _pace(recent, MIN_WINDOW_SPAN_DAYS)
        if pace is not None:
            return pace

    # Nothing recent enough to be a pace: the whole history is all we have.
    lifetime = _pace(logs, min_span_days=1)
    return lifetime if lifetime is not None else DEFAULT_AVG_DAILY_KM


def effective_avg_daily_km(
    car: Car, logs: Sequence[LogEntry], today: dt.date | None = None
) -> float:
    """The pace to forecast with: the owner's override, else the computed one.

    The override exists because no window can know about a coming move, a new
    job or a winter in the garage; when it is set, the computed value is only
    shown as a hint.
    """
    override = car.avg_daily_km_override
    if override is not None and override > 0:
        return float(override)
    return compute_avg_daily_km(logs, today=today)


def compute_interval_status(
    interval: ServiceInterval,
    current_odometer: int,
    avg_daily_km: float,
    today: dt.date | None = None,
) -> dict:
    if today is None:
        today = dt.date.today()

    due_odometer: int | None = None
    if interval.interval_km is not None and interval.last_odometer is not None:
        due_odometer = interval.last_odometer + interval.interval_km

    due_date: dt.date | None = None
    if interval.interval_days is not None and interval.last_date is not None:
        due_date = interval.last_date + dt.timedelta(days=interval.interval_days)

    km_left: int | None = None
    if due_odometer is not None:
        km_left = due_odometer - current_odometer

    days_left: int | None = None
    if due_date is not None:
        days_left = (due_date - today).days

    # Predicted due date: project km_left at the car's average daily pace;
    # if a calendar due date exists and is sooner, it wins.
    candidates: list[dt.date] = []
    if km_left is not None and avg_daily_km > 0:
        try:
            candidates.append(today + dt.timedelta(days=km_left / avg_daily_km))
        except OverflowError:
            # A near-zero pace projects beyond date.max: there is no
            # meaningful km-based prediction, so contribute no candidate.
            pass
    if due_date is not None:
        candidates.append(due_date)
    predicted_due_date = min(candidates) if candidates else None

    # Health: remaining fraction of the tighter of the km and days limits.
    fractions: list[float] = []
    if km_left is not None and interval.interval_km:
        fractions.append(km_left / interval.interval_km)
    if days_left is not None and interval.interval_days:
        fractions.append(days_left / interval.interval_days)
    if fractions:
        health_pct = min(fractions) * 100.0
        health_pct = max(0.0, min(100.0, health_pct))
    else:
        health_pct = 100.0
    health_pct = round(health_pct, 1)

    if (km_left is not None and km_left < 0) or (days_left is not None and days_left < 0):
        status = "overdue"
    elif (
        health_pct < 15.0
        or (km_left is not None and km_left < 1000)
        or (days_left is not None and days_left < 14)
    ):
        status = "due_soon"
    else:
        status = "ok"

    return {
        "due_odometer": due_odometer,
        "due_date": due_date,
        "km_left": km_left,
        "days_left": days_left,
        "predicted_due_date": predicted_due_date,
        "health_pct": health_pct,
        "status": status,
    }
