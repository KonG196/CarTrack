"""Vehicle lookup by plate or VIN through baza-gai.com.ua.

An intermediary on purpose: the state register itself is closed to private
services (ст. 34-1 ЗУ «Про дорожній рух» names a fixed list of recipients —
police, courts, МТСБУ, notaries), so a client of a licensed aggregator is the
only lawful shape this can take.

The free tier is small (~1000 lookups a month), so callers are rate-limited and
nothing is looked up twice: the answer goes straight into the car the user is
creating.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://baza-gai.com.ua"
_TIMEOUT_SECONDS = 15

# Their fuel vocabulary -> ours. Anything unmapped stays None: guessing the
# fuel of a car wrong is worse than leaving the field for the owner.
_FUEL_MAP = {
    "бензин": "petrol",
    "дизельне паливо": "diesel",
    "дизель": "diesel",
    "електро": "electric",
    "газ": "lpg",
    "газ пропан-бутан": "lpg",
    "газ метан": "lpg",
    "бензин/газ": "lpg",
    "гібрид": "hybrid",
}


class LookupUnavailable(Exception):
    """The service could not be reached or refused the key."""


def enabled() -> bool:
    return bool(settings.BAZA_GAI_API_KEY)


def normalize_plate(plate: str) -> str:
    """Strip everything but letters and digits, upper-case the rest."""
    return re.sub(r"[^0-9A-Za-zА-Яа-яІіЇїЄєҐґ]", "", plate).upper()


def _map_fuel(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    return _FUEL_MAP.get(raw.strip().lower())


def _shape(payload: dict[str, Any]) -> dict[str, Any]:
    """Reduce their answer to the fields a car profile actually has."""
    operations = payload.get("operations") or []
    latest = operations[0] if operations else {}
    fuel_raw = (latest.get("fuel") or {}).get("ua")
    displacement = latest.get("displacement") or None

    return {
        "plate": payload.get("digits"),
        "vin": payload.get("vin"),
        "brand": payload.get("vendor"),
        # Their model comes shouted («GOLF»); title case reads like a car, not
        # a headline, and the owner can always edit it.
        "model": (payload.get("model") or "").title() or None,
        "year": payload.get("model_year"),
        "fuel_type": _map_fuel(fuel_raw),
        "fuel_label": fuel_raw,
        "engine": f"{displacement / 1000:.1f}" if displacement else None,
        "color": (latest.get("color") or {}).get("ua"),
        "photo_url": payload.get("photo_url"),
        # The one thing here no logbook competitor offers: whether the car is
        # wanted. Never inferred — absent means we do not know, not "clean".
        "is_stolen": payload.get("is_stolen"),
        "stolen_details": payload.get("stolen_details"),
        "registrations": len(operations),
        "last_registered_at": latest.get("registered_at"),
    }


def lookup(query: str, by_vin: bool = False) -> Optional[dict[str, Any]]:
    """Look a car up by plate or VIN. None means the register has no such car."""
    if not enabled():
        raise LookupUnavailable("BAZA_GAI_API_KEY is not configured")

    value = query.strip().upper() if by_vin else normalize_plate(query)
    if not value:
        return None

    url = f"{_BASE_URL}/{'vin' if by_vin else 'nomer'}/{value}"
    try:
        response = httpx.get(
            url,
            headers={"Accept": "application/json", "X-Api-Key": settings.BAZA_GAI_API_KEY},
            timeout=_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise LookupUnavailable(str(exc)) from exc

    if response.status_code == 404:
        return None
    if response.status_code in (401, 403):
        raise LookupUnavailable("baza-gai rejected the API key")
    if response.status_code != 200:
        raise LookupUnavailable(f"baza-gai returned {response.status_code}")

    try:
        return _shape(response.json())
    except ValueError as exc:
        raise LookupUnavailable("baza-gai returned a non-JSON body") from exc
