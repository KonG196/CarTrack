"""Full-to-full fuel consumption engine.

Consumption is measured only between consecutive is_full_tank=True refuels.
Partial refuels accumulate their liters (and cost) into the next full-tank
segment. Segments with zero or negative odometer distance are skipped.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RefuelPoint:
    """A single refuel event, decoupled from the ORM layer."""

    date: dt.date
    odometer: int
    liters: float
    total_cost: float
    is_full_tank: bool


@dataclass(frozen=True)
class FuelSegment:
    """One measured full-to-full segment (keyed by the closing refuel)."""

    date: dt.date
    odometer: int
    distance_km: int
    liters: float
    consumption_l_100km: float


@dataclass
class FuelStats:
    """Aggregate fuel statistics for a car."""

    avg_consumption_l_100km: float | None
    last_consumption_l_100km: float | None
    avg_cost_per_km: float | None
    history: list[FuelSegment] = field(default_factory=list)


def compute_fuel_stats(refuels: Sequence[RefuelPoint]) -> FuelStats:
    """Compute full-to-full consumption stats from refuel events.

    The input is expected sorted by odometer ascending; it is re-sorted
    defensively. Refuels before the first full tank cannot be measured and
    are ignored. Every full tank becomes the new segment anchor even when
    its segment was skipped for zero/negative distance.
    """
    ordered = sorted(refuels, key=lambda r: (r.odometer, r.date))

    anchor: RefuelPoint | None = None
    accumulated_liters = 0.0
    accumulated_cost = 0.0

    history: list[FuelSegment] = []
    total_liters = 0.0
    total_cost = 0.0
    total_km = 0

    for point in ordered:
        if anchor is None:
            # No full-tank anchor yet: partials cannot be attributed to a
            # measurable segment, so only a full tank starts the tracking.
            if point.is_full_tank:
                anchor = point
                accumulated_liters = 0.0
                accumulated_cost = 0.0
            continue

        accumulated_liters += point.liters
        accumulated_cost += point.total_cost

        if not point.is_full_tank:
            continue

        distance_km = point.odometer - anchor.odometer
        if distance_km > 0 and accumulated_liters > 0:
            consumption = accumulated_liters / distance_km * 100.0
            history.append(
                FuelSegment(
                    date=point.date,
                    odometer=point.odometer,
                    distance_km=distance_km,
                    liters=round(accumulated_liters, 2),
                    consumption_l_100km=round(consumption, 2),
                )
            )
            total_liters += accumulated_liters
            total_cost += accumulated_cost
            total_km += distance_km

        # The full tank always becomes the new anchor; zero/negative
        # distance segments are simply skipped.
        anchor = point
        accumulated_liters = 0.0
        accumulated_cost = 0.0

    if total_km > 0:
        avg_consumption = round(total_liters / total_km * 100.0, 2)
        avg_cost_per_km = round(total_cost / total_km, 4)
    else:
        avg_consumption = None
        avg_cost_per_km = None

    last_consumption = history[-1].consumption_l_100km if history else None

    return FuelStats(
        avg_consumption_l_100km=avg_consumption,
        last_consumption_l_100km=last_consumption,
        avg_cost_per_km=avg_cost_per_km,
        history=history,
    )
