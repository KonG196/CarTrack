"""Tire domain logic that is not plain CRUD — the axle-rotation cadence.

Front tyres on a front-wheel-drive car wear faster, so makers advise swapping
the axles every ~10 000 km to even it out. This is the pure arithmetic of «is a
nudge due, and for which 10k mark», kept out of the bot so it can be tested on
its own.
"""

from __future__ import annotations

#: Rotate the axles every this many kilometres.
ROTATION_INTERVAL_KM = 10_000


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
