"""Gemini vision fallback for receipts that tesseract cannot read.

Used only when the local OCR pass recognized fewer than two money fields
and GEMINI_API_KEY is configured; the endpoint never fails because of this
fallback — any error here simply keeps the tesseract result.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import time
from typing import Any, Optional

import httpx

from app.config import settings
from app.services.ocr import (
    GAS_STATION_BRANDS,
    MAX_LITERS,
    MAX_PRICE_PER_LITER,
    MIN_PRICE_PER_LITER,
    MIN_TOTAL,
    ParsedReceipt,
    _fill_missing_third,
)

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
# The free tier is slow: a receipt photo takes ~40 s on a cold call.
_TIMEOUT_SECONDS = 90.0
# The free tier is also flaky (sporadic 503s): retry transient statuses a
# couple of times before giving up.
_RETRY_STATUSES = (429, 500, 502, 503)
_RETRY_DELAYS_SECONDS = (2.0, 5.0)

_PROMPT = """\
Це фото фіскального чека української АЗС. Витягни поля заправки і поверни
СУВОРО один JSON-обʼєкт без пояснень:
{"liters": число або null, "price_per_liter": число або null,
 "total_cost": число або null, "date": "YYYY-MM-DD" або null,
 "gas_station": "мережа АЗС" або null}

- liters і price_per_liter — з рядка відпуску пального (вигляд "43,06 л х 15,99":
  кількість літрів, потім ціна за літр).
- price_per_liter — саме ціна пального; НЕ податкова і НЕ знижкова ставка
  "грн/л" з інформаційних рядків.
- total_cost — фактично сплачена сума (СУМА / ДО СПЛАТИ), після знижки.
- Числа повертай з десятковою крапкою. Не вигадуй: якщо поля не видно — null.
"""


def _as_float(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ".").strip())
        except ValueError:
            return None
    return None


def _as_past_date(value: Any) -> Optional[dt.date]:
    if not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            parsed = dt.datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
        # a refuel receipt cannot be from the future
        return parsed if parsed <= dt.date.today() else None
    return None


def _canonical_station(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    lowered = value.strip().lower()
    for canonical, spellings in GAS_STATION_BRANDS:
        if any(spelling in lowered for spelling in spellings):
            return canonical
    return value.strip()[:100]


def parsed_receipt_from_llm(data: Any) -> Optional[ParsedReceipt]:
    if not isinstance(data, dict):
        return None
    liters = _as_float(data.get("liters"))
    price = _as_float(data.get("price_per_liter"))
    total = _as_float(data.get("total_cost"))
    if liters is not None and not 0 < liters <= MAX_LITERS:
        liters = None
    if price is not None and not MIN_PRICE_PER_LITER <= price <= MAX_PRICE_PER_LITER:
        price = None
    if total is not None and total < MIN_TOTAL:
        total = None
    result = ParsedReceipt(
        liters=liters,
        price_per_liter=price,
        total_cost=total,
        date=_as_past_date(data.get("date")),
        gas_station=_canonical_station(data.get("gas_station")),
        found_in_text=sum(v is not None for v in (liters, price, total)),
    )
    _fill_missing_third(result)
    return result


def recognize_receipt_llm(
    image_bytes: bytes, content_type: str
) -> Optional[ParsedReceipt]:
    if not settings.GEMINI_API_KEY:
        return None
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": _PROMPT},
                    {
                        "inlineData": {
                            "mimeType": content_type or "image/jpeg",
                            "data": base64.b64encode(image_bytes).decode(),
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0,
        },
    }
    # The key goes in a header, not a ?key= query param: new-style AI Studio
    # keys are rejected in the URL, and a header also keeps the key out of
    # error messages and access logs.
    for delay in (*_RETRY_DELAYS_SECONDS, None):
        response = httpx.post(
            _GEMINI_URL.format(model=settings.GEMINI_MODEL),
            headers={"x-goog-api-key": settings.GEMINI_API_KEY},
            json=payload,
            timeout=_TIMEOUT_SECONDS,
        )
        if response.status_code not in _RETRY_STATUSES or delay is None:
            break
        time.sleep(delay)
    response.raise_for_status()
    try:
        answer = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return parsed_receipt_from_llm(json.loads(answer))
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None
