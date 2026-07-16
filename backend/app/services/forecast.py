"""Forecast analytics: spending projections and upcoming service estimates."""

from __future__ import annotations

import calendar
import datetime as dt
import re
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Car, LogEntry, ServiceInterval
from app.services.baseline_costs import (
    CarProfile,
    baseline_cost,
    parse_displacement,
    parse_spec_litres,
)
from app.services.intervals import compute_interval_status, effective_avg_daily_km

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
    tokens = re.findall(r"\w+", text.lower())
    return {
        token
        for token in tokens
        if len(token) >= MIN_KEYWORD_LENGTH and token not in UKRAINIAN_STOP_WORDS
    }


def _log_service_text(log: LogEntry) -> str:
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


@dataclass(frozen=True)
class CostEstimate:
    amount: float
    # "history" — what this car was actually charged; "baseline" — a market
    # ballpark that knows nothing about this car. The two must never look alike
    # on screen: a guess wearing the authority of the user's own records is a
    # number they have no reason to check.
    source: str


def car_profile(car: Optional[Car]) -> CarProfile:
    """What the ballpark is allowed to know about this car.

    The oil volume comes off the owner's own spec sheet when they filled it —
    «Олива двигуна: ~4.6 л» is a fact transcribed from a service passport, and
    nothing derived can beat it. Otherwise the engine field is read for a
    displacement to derive one from.
    """
    if car is None:
        return CarProfile()
    oil_litres: Optional[float] = None
    for spec in car.specs or []:
        if "олив" in spec.name.lower() or "масл" in spec.name.lower():
            oil_litres = parse_spec_litres(spec.value)
            if oil_litres:
                break
    return CarProfile(
        fuel_type=car.fuel_type,
        displacement_l=parse_displacement(car.engine),
        oil_litres=oil_litres,
    )


def estimate_interval_cost(
    interval_title: str,
    logs: Sequence[LogEntry],
    car: Optional[Car] = None,
) -> Optional[CostEstimate]:
    """What the next one will cost: this car's own history, else the market.

    History wins whenever there is any — it knows the car, the shop and the city,
    and none of those are things a table can know.
    """
    title_keywords = normalize_keywords(interval_title)
    matched_costs: list[float] = []
    if title_keywords:
        for log in logs:
            if log.type not in ("maintenance", "repair"):
                continue
            if title_keywords & normalize_keywords(_log_service_text(log)):
                matched_costs.append(float(log.total_cost or 0))

    if matched_costs:
        return CostEstimate(round(median(matched_costs), 2), "history")

    ballpark = baseline_cost(interval_title, car_profile(car))
    if ballpark is None:
        return None
    return CostEstimate(ballpark, "baseline")


def build_forecast(
    db: Session,
    car: Car,
    today: dt.date | None = None,
    logs: Sequence[LogEntry] | None = None,
) -> dict:
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
                    selectinload(LogEntry.expense),
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

    avg_daily_km = effective_avg_daily_km(car, logs, today=today)
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
        estimate = estimate_interval_cost(interval.title, logs, car)
        upcoming.append(
            {
                "interval_id": interval.id,
                "title": interval.title,
                "predicted_due_date": predicted,
                "km_left": computed["km_left"],
                "days_left": computed["days_left"],
                "estimated_cost": estimate.amount if estimate else None,
                "estimated_cost_source": estimate.source if estimate else None,
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
