"""Offline climate calendar keyed off a Ukrainian plate — no weather API.

A plate's region maps to a climate zone, and each zone has a rough date for the
first sustained cold (time to fit winter tyres) and the first night frosts (time
for winter washer fluid). The dates come from long-run Ukrainian climate norms,
not a live forecast: the point is a timely nudge a fortnight before the queues,
not a precise prediction.

Region is read from the SECOND letter of the plate code, which identifies the
oblast across the common A/K/H/I series. It is a heuristic — enough to pick a
zone (west / centre / south-east), which is all the date needs — so the reminders
speak of «your region», never a named oblast that a rarer series might get wrong.
"""

from __future__ import annotations

import datetime as dt
import re

ZONE_WEST = "west"
ZONE_CENTER = "center"
ZONE_SOUTH_EAST = "south_east"

# Cyrillic plate letters fold to their Latin lookalikes: a plate may be typed
# in either alphabet, and only these twelve glyphs appear on Ukrainian plates.
_CYRILLIC_TO_LATIN = {
    "А": "A", "В": "B", "С": "C", "Е": "E", "Н": "H", "І": "I",
    "К": "K", "М": "M", "О": "O", "Р": "P", "Т": "T", "Х": "X",
}

# Second letter of the region code -> climate zone.
_SECOND_LETTER_ZONE = {
    "A": ZONE_CENTER,   # Київ
    "B": ZONE_CENTER,   # Вінницька
    "I": ZONE_CENTER,   # Київська
    "M": ZONE_CENTER,   # Житомирська
    "C": ZONE_WEST,     # Волинська
    "O": ZONE_WEST,     # Закарпатська
    "T": ZONE_WEST,     # Івано-Франківська
    "E": ZONE_SOUTH_EAST,  # Дніпропетровська
    "H": ZONE_SOUTH_EAST,  # Донецька
    "K": ZONE_SOUTH_EAST,  # Крим
    "P": ZONE_SOUTH_EAST,  # Запорізька
    "X": ZONE_SOUTH_EAST,  # Харківська
}

# (month, day) the reminder starts for each zone. The west cools first, the
# south-east last.
ZONE_TIRE_DATE = {
    ZONE_WEST: (10, 8),
    ZONE_CENTER: (10, 15),
    ZONE_SOUTH_EAST: (10, 25),
}
# Spring: time to move BACK onto summer tyres. The south-east warms first and
# the west last — the reverse order of autumn.
ZONE_TIRE_SPRING_DATE = {
    ZONE_SOUTH_EAST: (3, 25),
    ZONE_CENTER: (4, 1),
    ZONE_WEST: (4, 8),
}
ZONE_WASHER_DATE = {
    ZONE_WEST: (10, 20),
    ZONE_CENTER: (10, 27),
    ZONE_SOUTH_EAST: (11, 3),
}

# From the start date, how long the nudge stays live — long enough to survive a
# few days of the loop being down without the reminder being missed for a year.
REMINDER_WINDOW_DAYS = 14


def plate_zone(plate: str | None) -> str:
    """The climate zone for a plate, defaulting to centre for anything unknown."""
    code = "".join(
        _CYRILLIC_TO_LATIN.get(ch, ch)
        for ch in re.sub(r"[^0-9A-Za-zА-Яа-яІіЇїЄєҐґ]", "", plate or "").upper()
    )
    if len(code) < 2:
        return ZONE_CENTER
    return _SECOND_LETTER_ZONE.get(code[1], ZONE_CENTER)


def _in_window(plate: str | None, today: dt.date, zone_dates: dict[str, tuple[int, int]]) -> bool:
    month, day = zone_dates[plate_zone(plate)]
    start = dt.date(today.year, month, day)
    return start <= today <= start + dt.timedelta(days=REMINDER_WINDOW_DAYS)


def tire_changeover_due(plate: str | None, today: dt.date) -> bool:
    """Whether it is the fortnight to move this region onto winter tyres."""
    return _in_window(plate, today, ZONE_TIRE_DATE)


def tire_changeover_season(plate: str | None, today: dt.date) -> str | None:
    """The tyre season this region should move to now, or None.

    ``"winter"`` inside the autumn fortnight, ``"summer"`` inside the spring
    fortnight — the two windows when a swap is worth a nudge. Any other day is
    None. Drives the in-app «time to change over» banner both ways.
    """
    if _in_window(plate, today, ZONE_TIRE_DATE):
        return "winter"
    if _in_window(plate, today, ZONE_TIRE_SPRING_DATE):
        return "summer"
    return None


def washer_changeover_due(plate: str | None, today: dt.date) -> bool:
    """Whether it is the fortnight to switch to winter washer fluid."""
    return _in_window(plate, today, ZONE_WASHER_DATE)
