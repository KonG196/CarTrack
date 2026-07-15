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

import logging

from app.config import settings
from app.services import ocr_space
from app.services.ocr import (
    GAS_STATION_BRANDS,
    MAX_LITERS,
    MAX_PRICE_PER_LITER,
    MIN_PRICE_PER_LITER,
    MIN_TOTAL,
    ParsedReceipt,
    _fill_missing_third,
    extract_text,
    parse_receipt_text,
)

logger = logging.getLogger(__name__)

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

    # A rejected key and an overloaded model both end the request, but only one
    # of them is worth a human's attention — and a warning that says «fallback
    # failed» sends nobody to look at the key. Retrying it would be pointless
    # anyway: it will be just as invalid next time.
    if response.status_code in (401, 403):
        logger.error(
            "GEMINI_API_KEY was rejected (HTTP %s). Vision OCR is off until it "
            "is replaced: keys from aistudio.google.com/apikey look like "
            "'AIza…'; an OAuth token will not work here.",
            response.status_code,
        )
        return None
    response.raise_for_status()
    try:
        answer = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return parsed_receipt_from_llm(json.loads(answer))
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None


def recognize_receipt(image_bytes: bytes, content_type: str = "image/jpeg") -> ParsedReceipt:
    """Read a receipt: tesseract first, the vision model when it comes up short.

    The single entry point for every caller. It used to live inline in the API
    router, so the bot — which runs OCR in-process — quietly had no fallback at
    all: a crumpled photo simply failed there while the web read it fine.

    A failure of the remote model keeps the local result: nothing may break
    because someone else's API is down.
    """
    parsed = parse_receipt_text(extract_text(image_bytes))
    if parsed.found_in_text >= 2:
        return parsed

    # Rung two: OCR.space reads the pixels tesseract could not, and the same
    # parser reads its text. Free and cardless, so it is tried first.
    if ocr_space.enabled():
        try:
            remote_text = ocr_space.recognize_text(image_bytes, content_type)
        except Exception:
            logger.warning("OCR.space fallback failed", exc_info=True)
            remote_text = None
        if remote_text:
            # The text is what every wrong answer traces back to, and it is
            # invisible from the outside: a receipt read as «3.00 л × 13.99»
            # instead of «43,06 л × 15,99» looks like a parser bug until you
            # see that the reader never saw a 4.
            logger.info("OCR.space text:\n%s", remote_text)
            remote_parsed = parse_receipt_text(remote_text)
            if remote_parsed.found_in_text > parsed.found_in_text:
                parsed = remote_parsed
                if parsed.found_in_text >= 2:
                    return parsed

    # Rung three: a vision model that understands the receipt rather than
    # reading it. Costs money, so it goes last and only if configured.
    if not settings.GEMINI_API_KEY:
        return parsed
    try:
        llm_parsed = recognize_receipt_llm(image_bytes, content_type)
    except Exception:
        logger.warning("Vision fallback failed, keeping the local result", exc_info=True)
        return parsed
    if llm_parsed is not None and llm_parsed.found_in_text > parsed.found_in_text:
        return llm_parsed
    return parsed
