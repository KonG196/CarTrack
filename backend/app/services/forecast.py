"""Forecast analytics: spending projections and upcoming service estimates."""

from __future__ import annotations

import calendar
import datetime as dt
import re
from collections.abc import Sequence
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Car, LogEntry, ServiceInterval
from app.services.intervals import compute_avg_daily_km, compute_interval_status

UPCOMING_HORIZON_DAYS = 90
SPEND_WINDOW_DAYS = 90
MAX_SPEND_MONTHS = 6
MIN_KEYWORD_LENGTH = 4

# Generic service words that carry no information about WHAT was serviced.
# Matching on them would tie e.g. every "Заміна ..." interval to every log
# whose notes mention a replacement.
UKRAINIAN_STOP_WORDS = frozenset(
    {
        "заміна",
        "замінити",
        "замінено",
        "зміна",
        "перевірка",
        "перевірити",
        "перевірено",
        "ремонт",
        "огляд",
        "обслуговування",
        "встановлення",
        "встановлено",
        "установка",
        "кожні",
        "після",
        "перед",
        "разом",
        "також",
        "новий",
        "нова",
        "нове",
        "нові",
        "робота",
        "роботи",
        "інше",
        "інші",
    }
)


def normalize_keywords(text: str) -> set[str]:
    """Extract normalized keywords from free text.

    Keywords are lowercased word tokens of at least MIN_KEYWORD_LENGTH
    characters with Ukrainian stop-words removed.
    """
    tokens = re.findall(r"\w+", text.lower())
    return {
        token
        for token in tokens
        if len(token) >= MIN_KEYWORD_LENGTH and token not in UKRAINIAN_STOP_WORDS
    }


def _log_service_text(log: LogEntry) -> str:
    """Concatenate the searchable text of a maintenance/repair log entry."""
    parts: list[str] = []
    if log.maintenance is not None:
        parts.extend(log.maintenance.items or [])
    if log.repair is not None:
        parts.append(log.repair.category or "")
        if log.repair.part_name:
            parts.append(log.repair.part_name)
    if log.notes:
        parts.append(log.notes)
    return " ".join(parts)


def compute_monthly_km_rate(logs: Sequence[LogEntry]) -> float | None:
    """Average km driven per 30 days from the first/last log odometer span.

    Returns None with fewer than two logs, a date span under 7 days or a
    non-positive odometer delta.
    """
    if len(logs) < 2:
        return None

    ordered = sorted(logs, key=lambda log: (log.date, log.odometer))
    first, last = ordered[0], ordered[-1]

    day_span = (last.date - first.date).days
    odometer_delta = last.odometer - first.odometer
    if day_span < 7 or odometer_delta <= 0:
        return None

    return round(odometer_delta / day_span * 30.0, 1)


def compute_avg_monthly_spend(logs: Sequence[LogEntry], today: dt.date | None = None) -> float | None:
    """Mean total spend over the last complete calendar months with data.

    Considers only months strictly before the current one that contain at
    least one log, takes up to the MAX_SPEND_MONTHS most recent of them and
    averages their totals. Returns None when no complete month has data.
    """
    if today is None:
        today = dt.date.today()

    current = (today.year, today.month)
    totals: dict[tuple[int, int], float] = {}
    for log in logs:
        key = (log.date.year, log.date.month)
        if key >= current:
            continue
        totals[key] = totals.get(key, 0.0) + float(log.total_cost or 0)

    if not totals:
        return None

    recent = sorted(totals, reverse=True)[:MAX_SPEND_MONTHS]
    return round(sum(totals[key] for key in recent) / len(recent), 2)


def compute_projected_month_total(
    logs: Sequence[LogEntry], today: dt.date | None = None
) -> float | None:
    """Project the current calendar month's total spend.

    Spend so far this month plus the average daily spend rate of the last
    SPEND_WINDOW_DAYS days applied to the remaining days of the month.
    Returns None when there is no data in that window.
    """
    if today is None:
        today = dt.date.today()

    window_start = today - dt.timedelta(days=SPEND_WINDOW_DAYS - 1)
    window_spend = sum(
        float(log.total_cost or 0) for log in logs if window_start <= log.date <= today
    )
    has_window_data = any(window_start <= log.date <= today for log in logs)
    if not has_window_data:
        return None

    daily_rate = window_spend / SPEND_WINDOW_DAYS

    month_start = today.replace(day=1)
    spent_this_month = sum(
        float(log.total_cost or 0) for log in logs if month_start <= log.date <= today
    )

    days_in_month = calendar.monthrange(today.year, today.month)[1]
    remaining_days = days_in_month - today.day

    return round(spent_this_month + daily_rate * remaining_days, 2)


def estimate_interval_cost(interval_title: str, logs: Sequence[LogEntry]) -> float | None:
    """Estimate an interval's cost from this car's past service logs.

    A maintenance/repair log matches when its text (maintenance items,
    repair part_name/category, notes) shares at least one normalized keyword
    with the interval title. Returns the median total_cost of the matching
    logs, or None when nothing matches.
    """
    title_keywords = normalize_keywords(interval_title)
    if not title_keywords:
        return None

    matched_costs: list[float] = []
    for log in logs:
        if log.type not in ("maintenance", "repair"):
            continue
        if title_keywords & normalize_keywords(_log_service_text(log)):
            matched_costs.append(float(log.total_cost or 0))

    if not matched_costs:
        return None
    return round(median(matched_costs), 2)


def build_forecast(
    db: Session,
    car: Car,
    today: dt.date | None = None,
    logs: Sequence[LogEntry] | None = None,
) -> dict:
    """Assemble the forecast payload for a car per the API contract.

    ``logs`` lets callers that already loaded the car's log entries (with
    detail rows eager-loaded) reuse them instead of re-querying.
    """
    if today is None:
        today = dt.date.today()

    if logs is None:
        logs = (
            db.execute(
                select(LogEntry)
                .where(LogEntry.car_id == car.id)
                .order_by(LogEntry.date, LogEntry.odometer)
                .options(
                    selectinload(LogEntry.refuel),
                    selectinload(LogEntry.maintenance),
                    selectinload(LogEntry.repair),
                )
            )
            .scalars()
            .all()
        )
    intervals = (
        db.execute(
            select(ServiceInterval)
            .where(ServiceInterval.car_id == car.id)
            .order_by(ServiceInterval.id)
        )
        .scalars()
        .all()
    )

    avg_daily_km = compute_avg_daily_km(logs)
    horizon = today + dt.timedelta(days=UPCOMING_HORIZON_DAYS)

    upcoming: list[dict] = []
    for interval in intervals:
        computed = compute_interval_status(
            interval=interval,
            current_odometer=car.current_odometer,
            avg_daily_km=avg_daily_km,
            today=today,
        )
        predicted: dt.date | None = computed["predicted_due_date"]
        include = computed["status"] in ("due_soon", "overdue") or (
            predicted is not None and predicted <= horizon
        )
        if not include:
            continue
        upcoming.append(
            {
                "interval_id": interval.id,
                "title": interval.title,
                "predicted_due_date": predicted,
                "km_left": computed["km_left"],
                "days_left": computed["days_left"],
                "estimated_cost": estimate_interval_cost(interval.title, logs),
            }
        )

    upcoming.sort(
        key=lambda item: (
            item["predicted_due_date"] is None,
            item["predicted_due_date"] or dt.date.max,
        )
    )

    return {
        "monthly_km_rate": compute_monthly_km_rate(logs),
        "avg_monthly_spend": compute_avg_monthly_spend(logs, today),
        "projected_month_total": compute_projected_month_total(logs, today),
        "upcoming": upcoming,
    }
