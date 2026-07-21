"""Tire domain logic that is not plain CRUD — the axle-rotation cadence.

Front tyres on a front-wheel-drive car wear faster, so makers advise swapping
the axles every ~10 000 km to even it out. This is the pure arithmetic of «is a
nudge due, and for which 10k mark», kept out of the bot so it can be tested on
its own.
"""

from __future__ import annotations

import datetime as dt

#: Rotate the axles every this many kilometres.
ROTATION_INTERVAL_KM = 10_000

#: Warn to inspect tyres once they reach this age: rubber hardens and cracks
#: with time regardless of tread depth, so an old set is worth a look.
TIRE_AGE_WARN_YEARS = 4
#: Past this age replacement is usually overdue — the compound is well past its
#: prime even if the tread still looks fine.
TIRE_AGE_CRIT_YEARS = 8


def tire_age_years(
    dot_year: int | None, purchased_at: dt.date | None, today: dt.date
) -> int | None:
    """Age of a tyre set in whole years, or None when it cannot be known.

    The DOT production year is the honest measure — rubber ages from the day it
    was made, not the day it was fitted — so it wins; the purchase year is only
    a fallback for a set entered without a DOT. Never negative (a future year is
    a typo, not a time machine).
    """
    base_year = (
        dot_year
        if dot_year is not None
        else (purchased_at.year if purchased_at is not None else None)
    )
    if base_year is None:
        return None
    return max(0, today.year - base_year)


def is_tire_age_due(age_years: int | None) -> bool:
    """Whether a set is old enough to warrant an inspect-or-replace nudge."""
    return age_years is not None and age_years >= TIRE_AGE_WARN_YEARS


def due_rotation_km(
    km_since_rotation: int | None, reminded_km: int | None
) -> int | None:
    """The km-multiple to nudge about now, or None.

    Fires once per 10k crossed since the last rotation: at 10 000, again at
    20 000, and so on — never twice for the same mark. ``reminded_km`` is the
    last mark already nudged (0/None if never), which the caller stamps.
    """
    if km_since_rotation is None or km_since_rotation < ROTATION_INTERVAL_KM:
        return None
    reached = (km_since_rotation // ROTATION_INTERVAL_KM) * ROTATION_INTERVAL_KM
    if reached > (reminded_km or 0):
        return reached
    return None
