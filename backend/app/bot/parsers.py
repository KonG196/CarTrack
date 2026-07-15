"""Pure text parsers for incoming Telegram messages (no I/O)."""

from __future__ import annotations

import re
from typing import Optional

MIN_ODOMETER = 1
MAX_ODOMETER = 2_000_000

_ODOMETER_RE = re.compile(r"\d+")
# "<title> <amount>": the title must contain at least one non-space character
# before the trailing amount, so a bare number never matches (that is an
# odometer update, not an expense).
_QUICK_EXPENSE_RE = re.compile(r"(?P<title>.*\S)\s+(?P<amount>\d+(?:[.,]\d{1,2})?)")

_REFUEL_PREFIX_RE = re.compile(r"^заправ\w*", re.IGNORECASE)
_REFUEL_NUMBER = r"\d+(?:[.,]\d+)?"
_REFUEL_LITERS_RE = re.compile(
    rf"(?<![\d.,/])({_REFUEL_NUMBER})[ \t]*(?:л|l)\b", re.IGNORECASE
)
_REFUEL_PRICE_RE = re.compile(
    rf"({_REFUEL_NUMBER})[ \t]*(?:грн\.?)?[ \t]*/[ \t]*(?:л|l)\b", re.IGNORECASE
)
_REFUEL_PLAIN_NUMBER_RE = re.compile(rf"(?<![\d.,/])({_REFUEL_NUMBER})")


def parse_odometer(text: str) -> Optional[int]:
    """Parse a plain odometer message: an integer between 1 and 2,000,000.

    Decimals, signs and any surrounding words are rejected; only outer
    whitespace is stripped.
    """
    value = text.strip()
    if _ODOMETER_RE.fullmatch(value) is None:
        return None
    number = int(value)
    if not MIN_ODOMETER <= number <= MAX_ODOMETER:
        return None
    return number


def parse_quick_expense(text: str) -> Optional[tuple[str, float]]:
    match = _QUICK_EXPENSE_RE.fullmatch(text.strip())
    if match is None:
        return None
    title = match.group("title").strip()
    amount = float(match.group("amount").replace(",", "."))
    if not title or amount <= 0:
        return None
    return title, amount


def _refuel_float(raw: str) -> float:
    return float(raw.replace(",", "."))


def _blank_out(text: str, span: tuple[int, int]) -> str:
    """Remove an already-consumed match so its digits cannot match again."""
    start, end = span
    return f"{text[:start]} {text[end:]}"


def parse_refuel(text: str) -> Optional[dict]:
    """Parse a refuel message like «заправка 45л 2500» into refuel fields.

    Recognizes the liters ("45л" / "45,5 л" / "40 L") plus either the amount
    paid ("2500") or the unit price ("55.99 грн/л"); the third value is
    derived from the other two exactly as the OCR service does for receipts
    (rounded to two decimals). The message must open with «заправ...», there
    must be liters and no more than one leftover number — anything else is
    too ambiguous to guess at and returns None, leaving the message to the
    quick-expense parser.

    Returns {"liters", "price_per_liter", "total_cost"} or None. Pure: the
    caller decides which car the refuel belongs to and confirms it.
    """
    stripped = text.strip()
    prefix = _REFUEL_PREFIX_RE.match(stripped)
    if prefix is None:
        return None
    rest = _blank_out(stripped, prefix.span())

    liters_match = _REFUEL_LITERS_RE.search(rest)
    if liters_match is None:
        return None
    liters = _refuel_float(liters_match.group(1))
    if liters <= 0:
        return None
    rest = _blank_out(rest, liters_match.span())

    price_per_liter: Optional[float] = None
    price_match = _REFUEL_PRICE_RE.search(rest)
    if price_match is not None:
        price_per_liter = _refuel_float(price_match.group(1))
        rest = _blank_out(rest, price_match.span())

    total_cost: Optional[float] = None
    leftovers = _REFUEL_PLAIN_NUMBER_RE.findall(rest)
    if len(leftovers) > 1:
        # Two unlabelled numbers: no way to tell the total from a typo.
        return None
    if leftovers:
        total_cost = _refuel_float(leftovers[0])

    if price_per_liter is None and total_cost is None:
        return None
    if (price_per_liter is not None and price_per_liter <= 0) or (
        total_cost is not None and total_cost <= 0
    ):
        return None

    if total_cost is None:
        total_cost = round(liters * price_per_liter, 2)
    elif price_per_liter is None:
        price_per_liter = round(total_cost / liters, 2)

    return {
        "liters": liters,
        "price_per_liter": price_per_liter,
        "total_cost": total_cost,
    }
