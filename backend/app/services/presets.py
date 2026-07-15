"""Ready-made service-interval sets offered when a car has none yet.

Two groups: manufacturer maintenance (km-driven, some with a calendar
backstop) and Ukrainian compliance paperwork (date-only — a policy expires
on a date, not at an odometer reading).
"""

from __future__ import annotations

from typing import NamedTuple


class IntervalPreset(NamedTuple):

    title: str
    interval_km: int | None
    interval_days: int | None


MAINTENANCE_PRESETS: tuple[IntervalPreset, ...] = (
    IntervalPreset("Олива двигуна", 10000, 365),
    IntervalPreset("Повітряний фільтр", 20000, None),
    IntervalPreset("Паливний фільтр", 30000, None),
    IntervalPreset("Салонний фільтр", 15000, 365),
    IntervalPreset("ГРМ", 120000, None),
    IntervalPreset("Гальмівна рідина", 60000, 730),
)

COMPLIANCE_PRESETS: tuple[IntervalPreset, ...] = (
    IntervalPreset("Поліс ОСЦПВ", None, 365),
    IntervalPreset("Техогляд", None, 730),
    IntervalPreset("Зелена карта", None, 365),
    IntervalPreset("Транспортний податок", None, 365),
)
