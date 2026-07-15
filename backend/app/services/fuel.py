"""Full-to-full fuel consumption engine.

Consumption is measured only between consecutive is_full_tank=True refuels.
Partial refuels accumulate their liters (and cost) into the next full-tank
segment. Segments with zero or negative odometer distance are skipped.

A car may run on more than one fuel (ГБО: petrol and gas), and each tank is
its own independent full-to-full cycle — see ``compute_fuel_stats``.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Optional, Protocol

#: The range estimate is rounded to this step: it rests on an average
#: consumption, so a to-the-kilometre answer would claim a precision it has
#: not got.
RANGE_STEP_KM = 10

#: What may be recorded on a single refuel. A car's ``fuel_type`` has a wider
#: vocabulary (it also knows 'hybrid') and a NULL fuel_kind resolves to it, so
#: an EFFECTIVE kind is not restricted to this tuple.
REFUEL_FUEL_KINDS: tuple[str, ...] = ("petrol", "diesel", "lpg", "electric")


class CarLike(Protocol):
    """Only the part of a Car the fuel engine reads.

    Structural rather than an ``app.models.Car`` import: the engine stays free
    of the ORM (and of the import cycle that would come with it), while a real
    Car still satisfies it.
    """

    fuel_type: str


class RefuelLike(Protocol):
    """Only the part of a RefuelDetails the fuel engine reads."""

    fuel_kind: Optional[str]


def resolve_fuel_kind(fuel_kind: str | None, car: CarLike) -> str:
    """Resolve a stored (possibly NULL) fuel kind against its car.

    NULL means «whatever this car runs on»: that is what every pre-ГБО row
    holds, and what a single-fuel car goes on writing forever. Resolving it
    here — and only here — is what lets the rest of the app treat a legacy row
    and an explicit one as the same thing.
    """
    return fuel_kind or car.fuel_type


def effective_fuel_kind(refuel: RefuelLike, car: CarLike) -> str:
    return resolve_fuel_kind(refuel.fuel_kind, car)


@dataclass(frozen=True)
class RefuelPoint:
    """A single refuel event, decoupled from the ORM layer.

    ``log_id`` is an opaque caller-supplied identity: the engine only carries
    it onto the segment a refuel closes, so callers can map segments back to
    their own rows without re-deriving the math.

    ``fuel_kind`` is the EFFECTIVE kind — already resolved against the car by
    ``effective_fuel_kind`` — never the raw NULL out of the database.
    """

    date: dt.date
    odometer: int
    liters: float
    total_cost: float
    is_full_tank: bool
    log_id: int | None = None
    fuel_kind: str | None = None


@dataclass(frozen=True)
class FuelSegment:

    date: dt.date
    odometer: int
    distance_km: int
    liters: float
    consumption_l_100km: float
    log_id: int | None = None
    start_log_id: int | None = None


@dataclass
class FuelStats:

    avg_consumption_l_100km: float | None
    last_consumption_l_100km: float | None
    avg_cost_per_km: float | None
    history: list[FuelSegment] = field(default_factory=list)
    # Every litre bought and every hryvnia spent, including the fills no
    # segment could measure (the first one; a last one still open). The
    # averages above stay measured-only — these are «what left the wallet».
    total_liters: float = 0.0
    total_cost: float = 0.0


def compute_range_km(
    tank_liters: float | None, avg_consumption_l_100km: float | None
) -> int | None:
    """How far a FULL tank goes at this car's average consumption.

    Deliberately not «how far you can still drive»: nothing in the app knows
    the current tank level, so the answer is only ever the full-tank figure
    and the UI must say so.

    Returns None when either input is missing or non-positive — a car with no
    tank volume set, or with no measurable full-to-full segment yet, simply
    has no estimate. Rounded to RANGE_STEP_KM, half-up: the stdlib round() is
    banker's, and an exact 625 answering 620 reads as a lost 10 km.
    """
    if not tank_liters or not avg_consumption_l_100km:
        return None
    if tank_liters <= 0 or avg_consumption_l_100km <= 0:
        return None

    raw_km = tank_liters / avg_consumption_l_100km * 100.0
    return int(math.floor(raw_km / RANGE_STEP_KM + 0.5)) * RANGE_STEP_KM


def compute_fuel_stats(
    refuels: Sequence[RefuelPoint], fuel_kind: str | None = None
) -> FuelStats:
    """Compute full-to-full consumption stats from refuel events.

    The input is expected sorted by odometer ascending; it is re-sorted
    defensively. Refuels before the first full tank cannot be measured and
    are ignored. Every full tank becomes the new segment anchor even when
    its segment was skipped for zero/negative distance.

    ``fuel_kind`` narrows the measurement to one fuel, and this is the whole
    ГБО rule: on a dual-fuel car the petrol tank and the gas tank are
    INDEPENDENT full-to-full cycles. Only refuels of ``fuel_kind`` anchor,
    close or feed a segment — a petrol fill in the middle of a gas segment is
    invisible to it and must not break it. The DISTANCE, though, still spans
    everything in between, because those kilometres were genuinely driven: you
    do drive on the other fuel too. The result is litres of this fuel per 100
    km of driving, which is the only figure a dual-fuel car can honestly
    report.

    ``None`` measures every refuel together — exactly what a single-fuel car
    has always done, and what it goes on doing (all its refuels resolve to the
    one kind, so filtering by that kind changes nothing).
    """
    if fuel_kind is not None:
        refuels = [point for point in refuels if point.fuel_kind == fuel_kind]
    ordered = sorted(refuels, key=lambda r: (r.odometer, r.date))

    anchor: RefuelPoint | None = None
    accumulated_liters = 0.0
    accumulated_cost = 0.0

    history: list[FuelSegment] = []
    total_liters = 0.0
    total_cost = 0.0
    total_km = 0
    bought_liters = 0.0
    bought_cost = 0.0

    for point in ordered:
        bought_liters += point.liters
        bought_cost += point.total_cost

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
                    log_id=point.log_id,
                    start_log_id=anchor.log_id,
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
        total_liters=round(bought_liters, 2),
        total_cost=round(bought_cost, 2),
    )


def fuel_kinds_present(refuels: Sequence[RefuelPoint]) -> list[str]:
    kinds: list[str] = []
    for point in refuels:
        if point.fuel_kind is not None and point.fuel_kind not in kinds:
            kinds.append(point.fuel_kind)
    return kinds


def compute_stats_per_kind(refuels: Sequence[RefuelPoint]) -> dict[str, FuelStats]:
    """One independent FuelStats per fuel kind the car actually used.

    A single-fuel car yields exactly one entry, identical to the unfiltered
    run — which is the point of resolving NULL kinds before they get here.
    """
    return {
        kind: compute_fuel_stats(refuels, fuel_kind=kind)
        for kind in fuel_kinds_present(refuels)
    }
