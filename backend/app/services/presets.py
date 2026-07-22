"""Ready-made service-interval sets offered when a car has none yet.

Two groups: manufacturer maintenance (km-driven, some with a calendar
backstop) and Ukrainian compliance paperwork (date-only — a policy expires
on a date, not at an odometer reading).

Titles are seeded in the requesting user's language and STORED as-is (a preset
just fills the title field). Ukrainian titles keep matching baseline costs by
their stems; English titles are matched by the English baselines added in
``baseline_costs.py``. See ``presets_for``.
"""

from __future__ import annotations

from typing import NamedTuple

from app.i18n import normalize_lang


class IntervalPreset(NamedTuple):

    title: str
    interval_km: int | None
    interval_days: int | None


# (uk title, en title, interval_km, interval_days)
_MAINTENANCE: tuple[tuple[str, str, int | None, int | None], ...] = (
    ("Олива двигуна", "Engine oil", 10000, 365),
    ("Повітряний фільтр", "Air filter", 20000, None),
    ("Паливний фільтр", "Fuel filter", 30000, None),
    ("Салонний фільтр", "Cabin filter", 15000, 365),
    ("ГРМ", "Timing belt", 120000, None),
    ("Гальмівна рідина", "Brake fluid", 60000, 730),
)

_COMPLIANCE: tuple[tuple[str, str, int | None, int | None], ...] = (
    ("Поліс ОСЦПВ", "MTPL insurance", None, 365),
    ("Техогляд", "Roadworthiness test", None, 730),
    ("Зелена карта", "Green Card", None, 365),
    ("Транспортний податок", "Vehicle tax", None, 365),
)


def _build(rows, lang: str) -> tuple[IntervalPreset, ...]:
    en = normalize_lang(lang) == "en"
    return tuple(
        IntervalPreset(en_title if en else uk_title, km, days)
        for uk_title, en_title, km, days in rows
    )


def maintenance_presets(lang: str = "en") -> tuple[IntervalPreset, ...]:
    return _build(_MAINTENANCE, lang)


def compliance_presets(lang: str = "en") -> tuple[IntervalPreset, ...]:
    return _build(_COMPLIANCE, lang)


# Back-compat Ukrainian tuples (kept so existing imports/tests keep working).
MAINTENANCE_PRESETS: tuple[IntervalPreset, ...] = maintenance_presets("uk")
COMPLIANCE_PRESETS: tuple[IntervalPreset, ...] = compliance_presets("uk")
