"""Starter cheat-sheet values offered when a car has no specs yet.

A preset is a convenience, not a source of truth: every row it creates is
editable and re-running a preset never touches a value the owner has already
changed. There is deliberately no global specification database behind this —
keeping one accurate for every car on the road is not a promise this project
can keep.

Rows are seeded in the requesting user's language. The ``category`` stays a
canonical (Ukrainian) value from ``schemas.SPEC_CATEGORIES`` — only its display
is localized (frontend ``specCategoryLabel``); the ``name`` and ``value`` are
seeded in the user's language.
"""

from __future__ import annotations

from typing import NamedTuple

from app.i18n import normalize_lang


class SpecPreset(NamedTuple):

    category: str
    name: str
    value: str


# (canonical category, name_uk, name_en, value_uk, value_en). Transcribed from
# the owner's Golf 7 1.6 TDI (CXXB) service passport — recorded values, not
# derived ones. Do not add rows the passport does not have.
_GOLF7_16TDI: tuple[tuple[str, str, str, str, str], ...] = (
    ("Моменти затяжки", "Колісні болти", "Wheel bolts", "120 Нм", "120 N·m"),
    ("Моменти затяжки", "Пробка масляного піддону", "Oil drain plug", "30 Нм", "30 N·m"),
    ("Рідини та обʼєми", "Олива двигуна", "Engine oil", "~4.6 л", "~4.6 L"),
    ("Рідини та обʼєми", "Антифриз", "Antifreeze", "G13", "G13"),
    ("Допуски", "Допуск оливи", "Oil approval", "VW 507.00", "VW 507.00"),
    ("Допуски", "Паливо", "Fuel", "ДП Євро-5", "Diesel Euro-5"),
    ("Інше", "Код двигуна", "Engine code", "CXXB (EA288)", "CXXB (EA288)"),
    ("Інше", "Код КПП", "Gearbox code", "RTD (5-ст. механіка)", "RTD (5-speed manual)"),
    ("Інше", "Код фарби", "Paint code", "LI7F (Urano Gray)", "LI7F (Urano Gray)"),
)

_PRESETS = {"golf7_16tdi": _GOLF7_16TDI}

PRESET_KEYS = tuple(_PRESETS.keys())


def preset_for(key: str, lang: str = "en") -> tuple[SpecPreset, ...] | None:
    rows = _PRESETS.get(key)
    if rows is None:
        return None
    en = normalize_lang(lang) == "en"
    return tuple(
        SpecPreset(category, name_en if en else name_uk, value_en if en else value_uk)
        for category, name_uk, name_en, value_uk, value_en in rows
    )


# Back-compat: the Ukrainian sheet, keyed like before (used by tests / callers
# that don't pass a language).
SPEC_PRESETS: dict[str, tuple[SpecPreset, ...]] = {
    key: preset_for(key, "uk") for key in _PRESETS
}
GOLF7_16TDI = SPEC_PRESETS["golf7_16tdi"]
