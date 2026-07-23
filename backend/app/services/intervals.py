"""Service interval status and prediction engine."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

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


def sync_intervals_from_log(db: Session, log: LogEntry) -> list[ServiceInterval]:
    """Advance any service interval a maintenance log fulfils.

    A logbook entry that records a service ("Engine oil" at 168 000 km) should
    move the matching interval forward, the same way the one-tap «Done» button
    does — otherwise the journal and the intervals drift apart, and the owner
    who logs their oil change the ordinary way still sees the old due distance.

    Matching reuses the cost estimator's keyword rule (title keywords vs the
    log's service text), so what counts as "the oil-change interval" is decided
    in exactly one place. An interval is only ever moved *forward*: a log older
    than what the interval already records leaves it untouched, so backfilling
    ancient history can't un-service a car. Does not commit — the caller owns
    the transaction.
    """
    # Local import: forecast imports nothing from here, but keep the dependency
    # one-way and lazy so module import order never matters.
    from app.services.forecast import _log_service_text, normalize_keywords

    if log.type != "maintenance":
        return []
    log_keywords = normalize_keywords(_log_service_text(log))
    if not log_keywords:
        return []

    intervals = (
        db.execute(select(ServiceInterval).where(ServiceInterval.car_id == log.car_id))
        .scalars()
        .all()
    )
    advanced: list[ServiceInterval] = []
    for interval in intervals:
        # Compliance-only intervals (insurance, roadworthiness) are date rules a
        # service entry never satisfies; skip anything without a km rule.
        if interval.interval_km is None:
            continue
        if not (normalize_keywords(interval.title) & log_keywords):
            continue
        # Forward only, on either axis we track.
        newer_odo = interval.last_odometer is None or log.odometer > interval.last_odometer
        newer_date = interval.last_date is None or log.date >= interval.last_date
        if newer_odo and newer_date:
            interval.last_odometer = log.odometer
            interval.last_date = log.date
            interval.last_notified_at = None
            interval.snoozed_until = None
            advanced.append(interval)
    return advanced


def recompute_intervals_for_car(
    db: Session,
    car_id: int,
    removed_anchors: set[tuple[int, dt.date]] | None = None,
) -> list[ServiceInterval]:
    from app.services.forecast import _log_service_text, normalize_keywords

    logs = (
        db.execute(
            select(LogEntry)
            .where(LogEntry.car_id == car_id, LogEntry.type == "maintenance")
            .options(selectinload(LogEntry.maintenance))
        )
        .scalars()
        .all()
    )
    log_kw = [(log, normalize_keywords(_log_service_text(log))) for log in logs]

    intervals = (
        db.execute(select(ServiceInterval).where(ServiceInterval.car_id == car_id))
        .scalars()
        .all()
    )
    # Anchors that a maintenance log has ever set: (odometer, date) pairs across
    # the whole journal. An interval whose current anchor is one of these was
    # journal-derived, so it is safe to re-derive or clear it. An anchor that
    # matches no log was typed by hand — leave it alone.
    log_anchors = {(log.odometer, log.date) for log, _ in log_kw}
    if removed_anchors:
        log_anchors |= removed_anchors

    changed: list[ServiceInterval] = []
    for interval in intervals:
        if interval.interval_km is None:
            continue
        title_kw = normalize_keywords(interval.title)
        if not title_kw:
            continue
        best = None
        for log, kw in log_kw:
            if title_kw & kw and (best is None or (log.odometer, log.date) > (best.odometer, best.date)):
                best = log

        if best is not None:
            new_odo, new_date = best.odometer, best.date
        elif (interval.last_odometer, interval.last_date) in log_anchors:
            # The matching log that set this anchor is gone (deleted or edited to
            # no longer match) and nothing else matches: clear it, don't leave a
            # phantom "serviced" state.
            new_odo, new_date = None, None
        else:
            continue  # hand-entered anchor, or already unanchored — untouched

        if interval.last_odometer != new_odo or interval.last_date != new_date:
            interval.last_odometer = new_odo
            interval.last_date = new_date
            interval.last_notified_at = None
            interval.snoozed_until = None
            changed.append(interval)
    return changed


def seed_interval_from_history(db: Session, interval: ServiceInterval) -> bool:
    from app.services.forecast import _log_service_text, normalize_keywords

    if interval.last_odometer is not None or interval.last_date is not None:
        return False
    if interval.interval_km is None:
        return False
    title_keywords = normalize_keywords(interval.title)
    if not title_keywords:
        return False

    logs = (
        db.execute(
            select(LogEntry)
            .where(LogEntry.car_id == interval.car_id, LogEntry.type == "maintenance")
            .options(selectinload(LogEntry.maintenance))
        )
        .scalars()
        .all()
    )
    best = None
    for log in logs:
        if title_keywords & normalize_keywords(_log_service_text(log)):
            if best is None or (log.odometer, log.date) > (best.odometer, best.date):
                best = log
    if best is None:
        return False
    interval.last_odometer = best.odometer
    interval.last_date = best.date
    return True


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
