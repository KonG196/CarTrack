"""Offline VIN decoder: WMI lookup and ISO 3779 model year.

Deliberately a local table and nothing else. NHTSA vPIC — the only free VIN
API worth the round trip — fills just Make, Manufacturer, PlantCountry and
ModelYear for European VINs (16 of its 154 fields; Model, Fuel and
Displacement come back empty), which is exactly what the table below already
answers, offline and instantly. So: no network, no dependency, no key.

The check digit (position 9) is never verified. It is mandatory only in North
America; European manufacturers put a filler there — the owner's own Golf VII
reads WVWZZZAUZHP541983, whose Z would fail any check-digit test.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Optional

VIN_LENGTH = 17

# I, O and Q are excluded so they cannot be confused with 1 and 0.
VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")

# World Manufacturer Identifier (VIN positions 1-3) -> (manufacturer, country).
# Small on purpose: these are the makes a Ukrainian garage actually sees. An
# unknown WMI is not an error — the VIN is simply reported without a make.
WMI_TABLE: dict[str, tuple[str, str]] = {
    "WVW": ("Volkswagen", "Німеччина"),
    "WV1": ("Volkswagen", "Німеччина"),
    "WV2": ("Volkswagen", "Німеччина"),
    "WAU": ("Audi", "Німеччина"),
    "WA1": ("Audi", "Німеччина"),
    "WBA": ("BMW", "Німеччина"),
    "WBS": ("BMW", "Німеччина"),
    "WDB": ("Mercedes-Benz", "Німеччина"),
    "WDD": ("Mercedes-Benz", "Німеччина"),
    "W1K": ("Mercedes-Benz", "Німеччина"),
    "VF1": ("Renault", "Франція"),
    "VF3": ("Peugeot", "Франція"),
    "VF7": ("Citroën", "Франція"),
    "TMB": ("Škoda", "Чехія"),
    "ZFA": ("Fiat", "Італія"),
    "JMB": ("Mitsubishi", "Японія"),
    "JHM": ("Honda", "Японія"),
    "JN1": ("Nissan", "Японія"),
    "KMH": ("Hyundai", "Корея"),
    "KNA": ("Kia", "Корея"),
    "XTA": ("АвтоВАЗ (LADA)", "Росія"),
    "Y6D": ("ЗАЗ", "Україна"),
}

# ISO 3780 region digits: the country is known, the manufacturer is not.
REGION_PREFIXES: dict[str, str] = {
    "1": "США",
    "2": "Канада",
    "3": "Мексика",
    "4": "США",
    "5": "США",
}

# Position 10, in order: A=1980 … Y=2000, then 1=2001 … 9=2009, then the
# whole thing repeats (A=2010 … Y=2030). I, O, Q, U, Z and 0 never appear.
YEAR_LETTERS = "ABCDEFGHJKLMNPRSTVWXY"

# How long the position-10 alphabet takes to come back around.
YEAR_CYCLE = 30


def normalize_vin(value: Optional[str]) -> Optional[str]:
    """Upper-case and trim a VIN, or None when it is not one.

    Valid means 17 characters of the VIN alphabet — no check digit test, see
    the module docstring.
    """
    if not value:
        return None
    candidate = value.strip().upper()
    return candidate if VIN_PATTERN.match(candidate) else None


def decode_model_year(code: str, today: Optional[dt.date] = None) -> Optional[int]:
    if today is None:
        today = dt.date.today()

    if code.isdigit() and code != "0":
        base = 2000 + int(code)
    elif code in YEAR_LETTERS:
        base = 1980 + YEAR_LETTERS.index(code)
    else:
        return None

    year = base + YEAR_CYCLE
    if year > today.year + 1:
        year -= YEAR_CYCLE
    return year


def decode_vin(vin: Optional[str], today: Optional[dt.date] = None) -> dict:
    normalized = normalize_vin(vin)
    if normalized is None:
        return {
            "wmi": None,
            "manufacturer": None,
            "country": None,
            "model_year": None,
            "valid": False,
        }

    wmi = normalized[:3]
    manufacturer, country = WMI_TABLE.get(wmi, (None, None))
    if country is None:
        country = REGION_PREFIXES.get(wmi[0])

    return {
        "wmi": wmi,
        "manufacturer": manufacturer,
        "country": country,
        "model_year": decode_model_year(normalized[9], today=today),
        "valid": True,
    }
