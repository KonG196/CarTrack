"""Display unit system: metric (km, litres, l/100km) or imperial (mi, gal, mpg).

Presentation only — every value is STORED metric and converted here for the
report PDF and the Telegram digest. Mirrors frontend `src/units.js`.
"""

from __future__ import annotations

UNIT_SYSTEMS = ("metric", "imperial")
DEFAULT_UNIT_SYSTEM = "metric"

KM_PER_MILE = 1.609344
LITRES_PER_US_GALLON = 3.785411784
MPG_FROM_L100 = 235.214583  # mpg = MPG_FROM_L100 / (l/100km)


def normalize_unit_system(value: str | None, fallback: str = DEFAULT_UNIT_SYSTEM) -> str:
    code = str(value or "").strip().lower()
    return code if code in UNIT_SYSTEMS else fallback


def is_imperial(system: str | None) -> bool:
    return normalize_unit_system(system) == "imperial"


# Stored metric → displayed value in the chosen system.
def distance_from_km(km: float, system: str) -> float:
    return km / KM_PER_MILE if is_imperial(system) else km


def volume_from_litres(litres: float, system: str) -> float:
    return litres / LITRES_PER_US_GALLON if is_imperial(system) else litres


def consumption_from_l100(l100: float, system: str) -> float | None:
    if l100 is None or l100 <= 0:
        return None
    return MPG_FROM_L100 / l100 if is_imperial(system) else l100


def cost_per_distance_from_per_km(per_km: float, system: str) -> float:
    return per_km * KM_PER_MILE if is_imperial(system) else per_km


def distance_unit(system: str) -> str:
    return "mi" if is_imperial(system) else "km"


def volume_unit(system: str) -> str:
    return "gal" if is_imperial(system) else "L"


def consumption_unit(system: str) -> str:
    return "mpg" if is_imperial(system) else "L/100 km"
