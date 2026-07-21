"""«Ваш рік з Kapot» — a one-year recap of a car, for an in-app wrapped card.

Aggregates a single calendar year of a car's logs into a handful of headline
numbers (spend, litres, km, ₴/km, cheapest station, biggest bill, busiest
month). Reuses the shared fuel/station helpers so consumption and per-station
prices match the rest of Analytics.
"""

from __future__ import annotations

from app.models import Car, LogEntry
from app.services.fuel import compute_fuel_stats
from app.services.stats import build_refuel_points, compute_station_stats

LOG_TYPES = ("refuel", "maintenance", "repair", "expense")


def available_years(logs: list[LogEntry]) -> list[int]:
    """Years that have at least one log, newest first."""
    return sorted({log.date.year for log in logs}, reverse=True)


def _biggest_title(log: LogEntry) -> str:
    if log.type == "repair" and log.repair is not None:
        return log.repair.category or "Ремонт"
    if log.type == "expense" and log.expense is not None:
        return log.expense.category or "Витрата"
    if log.type == "refuel" and log.refuel is not None:
        return log.refuel.gas_station or "Заправка"
    if log.type == "maintenance":
        return "ТО"
    return "Запис"


def build_year_review(car: Car, logs: list[LogEntry], year: int) -> dict:
    year_logs = [log for log in logs if log.date.year == year]
    result: dict = {"year": year, "has_data": bool(year_logs), "available_years": available_years(logs)}
    if not year_logs:
        return result

    total_spent = sum(float(log.total_cost) for log in year_logs)
    by_type = {log_type: 0.0 for log_type in LOG_TYPES}
    month_counts: dict[int, int] = {}  # entries per month -> «найактивніший місяць»
    for log in year_logs:
        by_type[log.type] = by_type.get(log.type, 0.0) + float(log.total_cost)
        month_counts[log.date.month] = month_counts.get(log.date.month, 0) + 1

    refuels = [log for log in year_logs if log.type == "refuel" and log.refuel is not None]
    liters = sum(float(log.refuel.liters) for log in refuels)

    # Distance from odometer span, ignoring the 0 prefill (a fresh car's first
    # log saved at the default odometer) and other non-positive readings — one
    # stray 0 would otherwise blow km_driven (and ₴/km) up by ~100 000 km.
    driven = sorted(log.odometer for log in year_logs if log.odometer > 0)
    km_driven = driven[-1] - driven[0] if len(driven) >= 2 else 0

    fuel_stats = compute_fuel_stats(build_refuel_points(year_logs, car), fuel_kind=car.fuel_type)

    priced = [s for s in compute_station_stats(year_logs, car) if s["avg_price_per_liter"] is not None]
    cheapest = min(priced, key=lambda s: s["avg_price_per_liter"]) if priced else None

    biggest = max(year_logs, key=lambda log: float(log.total_cost))
    busiest_month = max(month_counts, key=month_counts.get) if month_counts else None

    result.update(
        {
            "total_spent": round(total_spent, 2),
            "by_type": {log_type: round(by_type[log_type], 2) for log_type in LOG_TYPES},
            "entries_count": len(year_logs),
            "refuels_count": len(refuels),
            "liters": round(liters, 1),
            "km_driven": km_driven,
            "cost_per_km": round(total_spent / km_driven, 2) if km_driven > 0 else None,
            "avg_consumption_l_100km": fuel_stats.avg_consumption_l_100km,
            "cheapest_station": (
                {"name": cheapest["name"], "avg_price_per_liter": cheapest["avg_price_per_liter"]}
                if cheapest
                else None
            ),
            "biggest_expense": {
                "type": biggest.type,
                "title": _biggest_title(biggest),
                "amount": round(float(biggest.total_cost), 2),
                "date": biggest.date.isoformat(),
            },
            "busiest_month": busiest_month,
        }
    )
    return result
