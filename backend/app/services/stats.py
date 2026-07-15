"""Analytics aggregation: spending totals, monthly buckets and fuel stats."""

from __future__ import annotations

import datetime as dt
from collections import Counter
from collections.abc import Sequence

from app.models import Car, LogEntry
from app.schemas import DEFAULT_EXPENSE_CATEGORY
from app.services.fuel import (
    FuelSegment,
    FuelStats,
    RefuelPoint,
    compute_fuel_stats,
    compute_stats_per_kind,
    effective_fuel_kind,
)

LOG_TYPES = ("refuel", "maintenance", "repair", "expense")

# Refuels with no station recorded still cost money, so they get a named
# bucket rather than being dropped from the per-station breakdown.
UNNAMED_STATION = "Без назви"

# How many refuels the price chart carries. A price trend is about the recent
# shape of the market, and a decade of points would be neither readable nor
# cheap to ship — so the OLDEST fall off, never the newest.
PRICE_HISTORY_LIMIT = 100


def month_key(day: dt.date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def last_n_month_keys(today: dt.date, n: int = 12) -> list[str]:
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


def build_refuel_points(logs: Sequence[LogEntry], car: Car) -> list[RefuelPoint]:
    """Convert refuel log entries (with details) into RefuelPoint values.

    The car is required because every point carries its EFFECTIVE fuel kind:
    NULL is resolved here, at the one boundary into the engine, so nothing
    downstream ever has to remember that NULL means «as the car».
    """
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
                log_id=log.id,
                fuel_kind=effective_fuel_kind(log.refuel, car),
            )
        )
    return points


def segments_per_kind(points: Sequence[RefuelPoint]) -> list[FuelSegment]:
    """Every measurable segment, each measured within its own fuel's cycle.

    A refuel belongs to exactly one kind, so it can anchor or close at most
    one segment overall and the segments never collide. A single-fuel car has
    one kind and gets back precisely what the unfiltered engine returns.
    """
    return [
        segment
        for stats in compute_stats_per_kind(points).values()
        for segment in stats.history
    ]


def consumption_by_log_id(logs: Sequence[LogEntry], car: Car) -> dict[int, float]:
    return {
        segment.log_id: segment.consumption_l_100km
        for segment in segments_per_kind(build_refuel_points(logs, car))
        if segment.log_id is not None
    }


def compute_price_history(logs: Sequence[LogEntry], car: Car) -> list[dict]:
    """Every refuel's price per litre, oldest first, newest PRICE_HISTORY_LIMIT.

    Sorted here rather than trusted from the caller: a backdated correction
    must land where it belongs on the timeline, not at the end of the list.
    """
    refuels = [log for log in logs if log.type == "refuel" and log.refuel is not None]
    refuels.sort(key=lambda log: (log.date, log.odometer, log.id))
    return [
        {
            "date": log.date,
            "price_per_liter": float(log.refuel.price_per_liter),
            "fuel_kind": effective_fuel_kind(log.refuel, car),
            "gas_station": log.refuel.gas_station,
        }
        for log in refuels[-PRICE_HISTORY_LIMIT:]
    ]


def compute_expense_by_category(logs: Sequence[LogEntry]) -> dict[str, float]:
    """Sum all-time expense spend per category.

    Only categories with entries are reported. Pre-0004 expenses have no
    category row and are counted under DEFAULT_EXPENSE_CATEGORY, the same
    bucket an expense created without a category lands in.
    """
    totals: dict[str, float] = {}
    for log in logs:
        if log.type != "expense":
            continue
        category = (
            log.expense.category if log.expense is not None else DEFAULT_EXPENSE_CATEGORY
        )
        totals[category] = totals.get(category, 0.0) + float(log.total_cost or 0)
    return {category: round(total, 2) for category, total in totals.items()}


def compute_station_stats(logs: Sequence[LogEntry], car: Car | None = None) -> list[dict]:
    """Aggregate refuel spend per gas station, priciest station first.

    Stations are grouped case-insensitively ('okko' and 'OKKO' are one
    station) and reported under their most-used spelling; ties keep the
    first-seen one so the name is stable across calls. Blank and missing
    names collapse into a single UNNAMED_STATION bucket.

    ``avg_consumption_l_100km`` averages the full-to-full segments that
    START at the station — the fuel burned over a segment is the fuel bought
    at its anchor, measured within that fuel's own cycle. Stations that never
    anchor a measurable segment (partials only, or a last fill whose segment
    never closed) report None. The fuel engine runs over the already-loaded
    logs, so this stays a single pass with no queries of its own.

    ``car`` is what resolves a NULL fuel kind, and is optional only to keep
    the aggregator callable on an empty history with nothing to resolve;
    without it no consumption is attributed and only the money is counted.
    """
    segments = segments_per_kind(build_refuel_points(logs, car)) if car is not None else []
    # An anchor opens at most one closed segment within its own kind, and a
    # refuel has exactly one kind, so start_log_id stays unique.
    consumption_by_start: dict[int, float] = {
        segment.start_log_id: segment.consumption_l_100km
        for segment in segments
        if segment.start_log_id is not None
    }

    groups: dict[str, dict] = {}
    for log in logs:
        if log.type != "refuel" or log.refuel is None:
            continue
        spelling = (log.refuel.gas_station or "").strip()
        key = spelling.casefold()
        group = groups.get(key)
        if group is None:
            group = {
                "spellings": Counter(),
                "refuels": 0,
                "total_liters": 0.0,
                "total_cost": 0.0,
                "consumptions": [],
            }
            groups[key] = group
        if spelling:
            group["spellings"][spelling] += 1
        group["refuels"] += 1
        group["total_liters"] += float(log.refuel.liters)
        group["total_cost"] += float(log.total_cost or 0)
        consumption = consumption_by_start.get(log.id)
        if consumption is not None:
            group["consumptions"].append(consumption)

    stations: list[dict] = []
    for key, group in groups.items():
        # Counter.most_common is stable, so an all-tied bucket keeps the
        # spelling that was inserted first.
        name = group["spellings"].most_common(1)[0][0] if key else UNNAMED_STATION
        total_liters = group["total_liters"]
        total_cost = group["total_cost"]
        consumptions = group["consumptions"]
        stations.append(
            {
                "name": name,
                "refuels": group["refuels"],
                "total_liters": round(total_liters, 2),
                "total_cost": round(total_cost, 2),
                "avg_price_per_liter": (
                    round(total_cost / total_liters, 2) if total_liters > 0 else None
                ),
                "avg_consumption_l_100km": (
                    round(sum(consumptions) / len(consumptions), 2)
                    if consumptions
                    else None
                ),
            }
        )

    # Name is the tie-breaker so equal-spend stations keep a stable order.
    stations.sort(key=lambda station: (-station["total_cost"], station["name"]))
    return stations


def compute_analytics(
    logs: Sequence[LogEntry], car: Car, today: dt.date | None = None
) -> dict:
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

    def serialize_history(segments: Sequence[FuelSegment]) -> list[dict]:
        return [
            {
                "date": segment.date,
                "odometer": segment.odometer,
                "distance_km": segment.distance_km,
                "liters": segment.liters,
                "consumption_l_100km": segment.consumption_l_100km,
            }
            for segment in segments
        ]

    points = build_refuel_points(logs, car)
    # The legacy `fuel.*` block is the car's OWN fuel, not a blend of both
    # tanks: an average over petrol and gas together is a number with no
    # physical meaning. For a single-fuel car every refuel resolves to
    # car.fuel_type anyway, so filtering by it changes precisely nothing —
    # which is what keeps the existing consumption suite green.
    fuel_stats: FuelStats = compute_fuel_stats(points, fuel_kind=car.fuel_type)
    per_kind = compute_stats_per_kind(points)

    return {
        "totals": {
            "all_time": round(all_time, 2),
            "this_month": round(this_month, 2),
            "by_type": {log_type: round(by_type[log_type], 2) for log_type in LOG_TYPES},
        },
        "monthly": monthly,
        "expense_by_category": compute_expense_by_category(logs),
        "stations": compute_station_stats(logs, car),
        "fuel": {
            "avg_consumption_l_100km": fuel_stats.avg_consumption_l_100km,
            "last_consumption_l_100km": fuel_stats.last_consumption_l_100km,
            "avg_cost_per_km": fuel_stats.avg_cost_per_km,
            "history": serialize_history(fuel_stats.history),
            "by_kind": {
                kind: {
                    "avg_consumption_l_100km": stats.avg_consumption_l_100km,
                    "last_consumption_l_100km": stats.last_consumption_l_100km,
                    "avg_cost_per_km": stats.avg_cost_per_km,
                    "total_liters": stats.total_liters,
                    "total_cost": stats.total_cost,
                    "history": serialize_history(stats.history),
                }
                for kind, stats in per_kind.items()
            },
        },
        "price_history": compute_price_history(logs, car),
    }
