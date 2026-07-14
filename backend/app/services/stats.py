"""Analytics aggregation: spending totals, monthly buckets and fuel stats."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from app.models import LogEntry
from app.services.fuel import FuelStats, RefuelPoint, compute_fuel_stats

LOG_TYPES = ("refuel", "maintenance", "repair", "expense")


def month_key(day: dt.date) -> str:
    """Format a date as its 'YYYY-MM' calendar month key."""
    return f"{day.year:04d}-{day.month:02d}"


def last_n_month_keys(today: dt.date, n: int = 12) -> list[str]:
    """The last n calendar months including the current one, oldest first."""
    keys: list[str] = []
    year, month = today.year, today.month
    for _ in range(n):
        keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    keys.reverse()
    return keys


def build_refuel_points(logs: Sequence[LogEntry]) -> list[RefuelPoint]:
    """Convert refuel log entries (with details) into RefuelPoint values."""
    points: list[RefuelPoint] = []
    for log in logs:
        if log.type != "refuel" or log.refuel is None:
            continue
        points.append(
            RefuelPoint(
                date=log.date,
                odometer=log.odometer,
                liters=float(log.refuel.liters),
                total_cost=float(log.total_cost or 0),
                is_full_tank=bool(log.refuel.is_full_tank),
            )
        )
    return points


def compute_analytics(logs: Sequence[LogEntry], today: dt.date | None = None) -> dict:
    """Build the analytics payload for a car from its full log history."""
    if today is None:
        today = dt.date.today()

    current_key = month_key(today)
    month_keys = last_n_month_keys(today, 12)
    buckets: dict[str, dict[str, float]] = {
        key: {log_type: 0.0 for log_type in LOG_TYPES} for key in month_keys
    }

    all_time = 0.0
    this_month = 0.0
    by_type = {log_type: 0.0 for log_type in LOG_TYPES}

    for log in logs:
        cost = float(log.total_cost or 0)
        all_time += cost
        by_type[log.type] += cost
        key = month_key(log.date)
        if key == current_key:
            this_month += cost
        if key in buckets:
            buckets[key][log.type] += cost

    monthly = []
    for key in month_keys:
        bucket = buckets[key]
        monthly.append(
            {
                "month": key,
                "refuel": round(bucket["refuel"], 2),
                "maintenance": round(bucket["maintenance"], 2),
                "repair": round(bucket["repair"], 2),
                "expense": round(bucket["expense"], 2),
                "total": round(sum(bucket.values()), 2),
            }
        )

    fuel_stats: FuelStats = compute_fuel_stats(build_refuel_points(logs))

    return {
        "totals": {
            "all_time": round(all_time, 2),
            "this_month": round(this_month, 2),
            "by_type": {log_type: round(by_type[log_type], 2) for log_type in LOG_TYPES},
        },
        "monthly": monthly,
        "fuel": {
            "avg_consumption_l_100km": fuel_stats.avg_consumption_l_100km,
            "last_consumption_l_100km": fuel_stats.last_consumption_l_100km,
            "avg_cost_per_km": fuel_stats.avg_cost_per_km,
            "history": [
                {
                    "date": segment.date,
                    "odometer": segment.odometer,
                    "distance_km": segment.distance_km,
                    "liters": segment.liters,
                    "consumption_l_100km": segment.consumption_l_100km,
                }
                for segment in fuel_stats.history
            ],
        },
    }
