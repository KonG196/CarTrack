"""Starter cheat-sheet values offered when a car has no specs yet.

A preset is a convenience, not a source of truth: every row it creates is
editable and re-running a preset never touches a value the owner has already
changed. There is deliberately no global specification database behind this —
keeping one accurate for every car on the road is not a promise this project
can keep.
"""

from __future__ import annotations

from typing import NamedTuple


class SpecPreset(NamedTuple):

    category: str
    name: str
    value: str


# Transcribed from the owner's Golf 7 1.6 TDI (CXXB) service passport. These
# are recorded values, not derived ones: do not add rows that are not in the
# passport, and do not "correct" the ones that are.
GOLF7_16TDI: tuple[SpecPreset, ...] = (
    SpecPreset("Моменти затяжки", "Колісні болти", "120 Нм"),
    SpecPreset("Моменти затяжки", "Пробка масляного піддону", "30 Нм"),
    SpecPreset("Рідини та обʼєми", "Олива двигуна", "~4.6 л"),
    SpecPreset("Рідини та обʼєми", "Антифриз", "G13"),
    SpecPreset("Допуски", "Допуск оливи", "VW 507.00"),
    SpecPreset("Допуски", "Паливо", "ДП Євро-5"),
    SpecPreset("Інше", "Код двигуна", "CXXB (EA288)"),
    SpecPreset("Інше", "Код КПП", "RTD (5-ст. механіка)"),
    SpecPreset("Інше", "Код фарби", "LI7F (Urano Gray)"),
)

SPEC_PRESETS: dict[str, tuple[SpecPreset, ...]] = {
    "golf7_16tdi": GOLF7_16TDI,
}
