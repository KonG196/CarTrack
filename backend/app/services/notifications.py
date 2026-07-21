"""In-app notification centre: the proactive nudges, computed on read.

The same signals the Telegram bot pushes — due/overdue service (including the
document-expiry intervals), a consumption spike, the seasonal tyre changeover,
axle rotation, tyre age and an expiring ОСЦПВ — assembled for the web app so a
driver who never linked the bot still sees them.

Read-only and per-request: nothing is stored, so there is no table to prune on
the small VM. The work is O(cars × logs) and no heavier than one Analytics load.
Dismiss is client-side (localStorage); each nudge carries a stable id so a
dismissal sticks until the nudge itself changes (a new due mark, a new year…).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Car, LogEntry, User
from app.services import climate
from app.services.fuel import compute_stats_per_kind, detect_consumption_spike
from app.services.intervals import compute_interval_status, effective_avg_daily_km
from app.services.stats import build_refuel_points
from app.services.tires import (
    TIRE_AGE_CRIT_YEARS,
    due_rotation_km,
    is_tire_age_due,
    tire_age_years,
)

#: Warn this many days before the ОСЦПВ lapses; escalate inside the last week.
INSURANCE_WARN_DAYS = 30
INSURANCE_CRIT_DAYS = 7
#: Stop nagging about a policy expired longer ago than this — the data is stale
#: (renewed elsewhere, or the car is long gone) rather than an active problem.
INSURANCE_STALE_DAYS = 60

_SEASON_ACCUSATIVE = {"winter": "зимову", "summer": "літню"}
_SEVERITY_RANK = {"crit": 0, "warn": 1, "info": 2}


def _car_label(car: Car) -> str:
    return f"{car.brand} {car.model}"


def _interval_body(status: dict) -> str:
    """«прострочено на… / залишилось…», hiding the axis that still has slack.

    Same rule as the dashboard row: once overdue, only what is overdue shows.
    """
    km_left = status["km_left"]
    days_left = status["days_left"]
    overdue = status["status"] == "overdue"
    parts: list[str] = []
    if km_left is not None:
        if km_left < 0:
            parts.append(f"прострочено на {abs(km_left)} км")
        elif not overdue:
            parts.append(f"залишилось {km_left} км")
    if days_left is not None:
        if days_left < 0:
            parts.append(f"{abs(days_left)} дн. тому")
        elif not overdue:
            parts.append(f"залишилось {days_left} дн.")
    if parts:
        return ", ".join(parts)
    return "вже прострочено" if overdue else "наближається"


def _insurance_body(until: dt.date, days_left: int) -> str:
    if days_left < 0:
        return (
            f"ОСЦПВ була дійсна до {until:%d.%m.%Y} — прострочено на {abs(days_left)} дн. "
            "Їзда без поліса — штраф і особиста відповідальність за ДТП."
        )
    return (
        f"ОСЦПВ дійсна до {until:%d.%m.%Y} — лишилось {days_left} дн. "
        "Оновіть поліс, щоб уникнути штрафу."
    )


def build_notifications(db: Session, user: User, today: dt.date | None = None) -> list[dict]:
    if today is None:
        today = dt.date.today()

    cars = (
        db.execute(
            select(Car)
            .where(Car.user_id == user.id)
            .options(
                selectinload(Car.intervals),
                selectinload(Car.tire_sets),
                selectinload(Car.documents),
                selectinload(Car.logs).selectinload(LogEntry.refuel),
            )
            .order_by(Car.id)
        )
        .scalars()
        .all()
    )

    items: list[dict] = []
    for car in cars:
        label = _car_label(car)
        logs = list(car.logs)
        avg_daily_km = effective_avg_daily_km(car, logs, today)

        # 1. Service + document-expiry intervals that are due or overdue.
        for interval in sorted(car.intervals, key=lambda i: i.id):
            status = compute_interval_status(interval, car.current_odometer, avg_daily_km, today)
            if status["status"] not in ("due_soon", "overdue"):
                continue
            overdue = status["status"] == "overdue"
            items.append(
                {
                    "id": f"interval:{interval.id}:{status['status']}",
                    "kind": "interval",
                    "severity": "crit" if overdue else "warn",
                    "car_id": car.id,
                    "car_label": label,
                    "title": interval.title,
                    "body": _interval_body(status),
                    "action": "/intervals",
                }
            )

        # 2. Consumption spike over the car's own recent baseline.
        spike = detect_consumption_spike(compute_stats_per_kind(build_refuel_points(logs, car)))
        if spike is not None:
            items.append(
                {
                    "id": f"spike:{spike.log_id}",
                    "kind": "spike",
                    "severity": "warn",
                    "car_id": car.id,
                    "car_label": label,
                    "title": "Стрибок витрати пального",
                    "body": (
                        f"+{spike.pct_over}% над нормою "
                        f"({spike.consumption_l_100km:.1f} проти ~{spike.baseline_l_100km:.1f} л/100 км). "
                        "Перевірте тиск у шинах, фільтри чи свічки."
                    ),
                    "action": "/analytics",
                }
            )

        mounted = next((tire_set for tire_set in car.tire_sets if tire_set.is_installed), None)

        # 3. Tyre age of the mounted set.
        if mounted is not None:
            age = tire_age_years(mounted.dot_year, mounted.purchased_at, today)
            if is_tire_age_due(age):
                items.append(
                    {
                        "id": f"tire_age:{mounted.id}:{today.year}",
                        "kind": "tire_age",
                        "severity": "crit" if age >= TIRE_AGE_CRIT_YEARS else "warn",
                        "car_id": car.id,
                        "car_label": label,
                        "title": "Вік шин",
                        "body": (
                            f"Комплекту «{mounted.name}» вже {age} р. — час перевірити стан "
                            "і, можливо, замінити."
                        ),
                        "action": "/tires",
                    }
                )

            # 4. Axle rotation of the mounted set.
            if mounted.odometer_at_rotation is not None:
                km_since = max(0, car.current_odometer - mounted.odometer_at_rotation)
                due_km = due_rotation_km(km_since, mounted.rotation_reminded_km)
                if due_km is not None:
                    items.append(
                        {
                            "id": f"rotation:{mounted.id}:{due_km}",
                            "kind": "rotation",
                            "severity": "warn",
                            "car_id": car.id,
                            "car_label": label,
                            "title": "Ротація шин",
                            "body": (
                                f"{km_since} км від останньої ротації — переставте вісі, "
                                "щоб протектор зношувався рівномірно."
                            ),
                            "action": "/tires",
                        }
                    )

        # 5. Seasonal changeover (region calendar): add tyres, or switch season.
        season = climate.tire_changeover_season(car.plate, today)
        if season is not None:
            if not car.tire_sets:
                items.append(
                    {
                        "id": f"seasonal:add:{car.id}:{today.year}:{season}",
                        "kind": "seasonal",
                        "severity": "info",
                        "car_id": car.id,
                        "car_label": label,
                        "title": "Сезон шиномонтажу",
                        "body": "Додайте свій комплект шин, і я нагадуватиму про заміну, ротацію та вік.",
                        "action": "/tires",
                    }
                )
            elif (
                mounted is not None
                and mounted.season != season
                and mounted.season != "all_season"
            ):
                items.append(
                    {
                        "id": f"seasonal:switch:{car.id}:{today.year}:{season}",
                        "kind": "seasonal",
                        "severity": "info",
                        "car_id": car.id,
                        "car_label": label,
                        "title": "Час міняти гуму",
                        "body": f"Пора переходити на {_SEASON_ACCUSATIVE[season]} гуму за сезоном.",
                        "action": "/tires",
                    }
                )

        # 6. ОСЦПВ expiry from the date field — only when no insurance DOCUMENT
        #    already books it (an uploaded policy surfaces as an interval above).
        #    Must be insurance-specific: a техогляд document also books a
        #    "(документ)" interval, and it must not silence the ОСЦПВ nudge.
        has_insurance_document = any(
            document.kind == "insurance" and document.expires_at is not None
            for document in car.documents
        )
        if car.insurance_until is not None and not has_insurance_document:
            days_left = (car.insurance_until - today).days
            if -INSURANCE_STALE_DAYS <= days_left <= INSURANCE_WARN_DAYS:
                items.append(
                    {
                        "id": f"insurance:{car.id}:{car.insurance_until.isoformat()}",
                        "kind": "insurance",
                        "severity": "crit" if days_left <= INSURANCE_CRIT_DAYS else "warn",
                        "car_id": car.id,
                        "car_label": label,
                        "title": "Страховка спливає" if days_left >= 0 else "Страховка прострочена",
                        "body": _insurance_body(car.insurance_until, days_left),
                        "action": "/documents",
                    }
                )

    items.sort(key=lambda note: _SEVERITY_RANK.get(note["severity"], 3))
    return items
