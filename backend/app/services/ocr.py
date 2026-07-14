"""Receipt OCR: image -> raw text (tesseract) and raw text -> refuel fields."""

from __future__ import annotations

import datetime as dt
import io
import re
from dataclasses import dataclass
from typing import Optional

import pytesseract
from PIL import Image

# Canonical brand name -> spellings recognized in receipt text (lowercase,
# both Latin and Cyrillic variants).
GAS_STATION_BRANDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("OKKO", ("okko", "окко")),
    ("WOG", ("wog", "вог")),
    ("SOCAR", ("socar", "сокар")),
    ("UPG", ("upg",)),
    ("SHELL", ("shell", "шелл")),
    ("AMIC", ("amic", "амік")),
    ("БРСМ", ("брсм", "brsm")),
    ("АВІАС", ("авіас", "avias")),
    ("УКРНАФТА", ("укрнафта", "ukrnafta")),
    ("KLO", ("klo", "кло")),
    ("MOTTO", ("motto", "мотто")),
    ("MARSHAL", ("marshal", "маршал")),
)

# Keywords marking the receipt total, in priority order: the paid-amount
# keyword goes last because it may exceed the actual total (cash + change).
TOTAL_KEYWORDS: tuple[str, ...] = ("до сплати", "сума", "разом", "total", "сплачено")

# Sanity cap for a single refuel: even a truck tank stays a few hundred
# liters, so anything above this is an OCR misread (serial numbers, coupons).
MAX_LITERS = 200.0

# A money-or-quantity token. Thousands-grouped alternatives go first so that
# "1 250.50" / "1.250,50" / "1,250.50" match as one token, not as fragments.
_NUMBER = (
    r"\d{1,3}(?:[ \u00A0]\d{3})+(?:[.,]\d+)?"  # 1 250 / 1 250.50
    r"|\d{1,3}(?:\.\d{3})+,\d+"  # 1.250,50
    r"|\d{1,3}(?:,\d{3})+\.\d+"  # 1,250.50
    r"|\d+(?:[.,]\d+)?"  # 2502.05 / 52,49
)
_NUMBER_RE = re.compile(_NUMBER)
_SPACE_GROUPED_RE = re.compile(r"\d{1,3}(?:[ \u00A0]\d{3})+(?:[.,]\d+)?")
_DOT_GROUPED_RE = re.compile(r"\d{1,3}(?:\.\d{3})+,\d+")
_COMMA_GROUPED_RE = re.compile(r"\d{1,3}(?:,\d{3})+\.\d+")
# A quantity looks like "45.50 Л" / "45,50 л" / "40 L"; the lookbehind keeps
# the match from starting mid-number or right after a slash (as in "грн/л").
_LITERS_RE = re.compile(rf"(?<![\d.,/])({_NUMBER})[ \t]*(?:л|l)\b", re.IGNORECASE)
_PRICE_PER_LITER_RE = re.compile(
    rf"({_NUMBER})[ \t]*(?:грн\.?)?[ \t]*/[ \t]*(?:л|l)\b", re.IGNORECASE
)
_PRICE_LABEL_RE = re.compile(r"ціна", re.IGNORECASE)
_DATE_RE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b")


@dataclass
class ParsedReceipt:
    """Structured fields recognized on a fuel receipt (None when not found)."""

    liters: Optional[float] = None
    price_per_liter: Optional[float] = None
    total_cost: Optional[float] = None
    date: Optional[dt.date] = None
    gas_station: Optional[str] = None


def extract_text(image_bytes: bytes) -> str:
    """OCR an image with tesseract, preferring Ukrainian + English.

    Falls back to English-only when the "ukr" traineddata is missing
    (pytesseract raises TesseractError for it). TesseractNotFoundError —
    the tesseract binary itself is absent — propagates to the caller.
    """
    image = Image.open(io.BytesIO(image_bytes))
    try:
        return pytesseract.image_to_string(image, lang="ukr+eng")
    except pytesseract.TesseractError:
        return pytesseract.image_to_string(image, lang="eng")


def _to_float(raw: str) -> float:
    """Parse a number with a decimal comma and/or thousands separators.

    Space (incl. non-breaking) groups are always thousands ("1 250.50");
    dot/comma groups count as thousands only when the other character is the
    decimal separator ("1.250,50" / "1,250.50"), so plain "1.250" keeps its
    current meaning of one-point-two-five.
    """
    raw = raw.replace("\u00a0", " ")
    if _SPACE_GROUPED_RE.fullmatch(raw):
        raw = raw.replace(" ", "")
    elif _DOT_GROUPED_RE.fullmatch(raw):
        raw = raw.replace(".", "")
    elif _COMMA_GROUPED_RE.fullmatch(raw):
        raw = raw.replace(",", "")
    return float(raw.replace(",", "."))


def _parse_liters(text: str) -> Optional[float]:
    for match in _LITERS_RE.finditer(text):
        value = _to_float(match.group(1))
        if 0 < value <= MAX_LITERS:
            return value
    return None


def _parse_price_per_liter(text: str) -> Optional[float]:
    match = _PRICE_PER_LITER_RE.search(text)
    if match:
        return _to_float(match.group(1))
    for line in text.splitlines():
        if _PRICE_LABEL_RE.search(line):
            numbers = _NUMBER_RE.findall(line)
            if numbers:
                return _to_float(numbers[0])
    return None


def _parse_total(text: str) -> Optional[float]:
    for keyword in TOTAL_KEYWORDS:
        candidates: list[float] = []
        for line in text.splitlines():
            if keyword in line.lower():
                # OCR may merge the price line into the total line: drop
                # per-liter price tokens ("54.99 ГРН/Л") so they cannot be
                # mistaken for the amount paid.
                cleaned = _PRICE_PER_LITER_RE.sub(" ", line)
                candidates.extend(
                    _to_float(raw) for raw in _NUMBER_RE.findall(cleaned)
                )
        if candidates:
            # Prefer the largest money-looking value on the total line(s):
            # smaller numbers there are usually VAT or quantities.
            return max(candidates)
    return None


def _parse_date(text: str) -> Optional[dt.date]:
    for match in _DATE_RE.finditer(text):
        day, month, year = (int(part) for part in match.groups())
        try:
            return dt.date(year, month, day)
        except ValueError:
            continue
    return None


def _parse_gas_station(text: str) -> Optional[str]:
    lowered = text.lower()
    for canonical, spellings in GAS_STATION_BRANDS:
        for spelling in spellings:
            if re.search(rf"\b{re.escape(spelling)}", lowered):
                return canonical
    return None


def _fill_missing_third(result: ParsedReceipt) -> None:
    """Compute the third of liters/price/total when exactly two are known."""
    liters, price, total = result.liters, result.price_per_liter, result.total_cost
    known = sum(value is not None for value in (liters, price, total))
    if known != 2:
        return
    if total is None:
        result.total_cost = round(liters * price, 2)
    elif price is None and liters:
        result.price_per_liter = round(total / liters, 2)
    elif liters is None and price:
        result.liters = round(total / price, 2)


def parse_receipt_text(text: str) -> ParsedReceipt:
    """Parse OCR'd Ukrainian fuel-receipt text into structured fields.

    Pure function (no I/O): recognizes liters ("45.50 Л"), the total
    (СУМА / ДО СПЛАТИ / РАЗОМ / TOTAL / СПЛАЧЕНО lines), the price per liter
    (ЦІНА / грн-per-liter markers), a dd.mm.yyyy-style date and known gas
    station brands. Decimal commas are normalized to dots and the missing
    third of (liters, price, total) is derived when exactly two are found.
    """
    result = ParsedReceipt(
        liters=_parse_liters(text),
        price_per_liter=_parse_price_per_liter(text),
        total_cost=_parse_total(text),
        date=_parse_date(text),
        gas_station=_parse_gas_station(text),
    )
    _fill_missing_third(result)
    return result
