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
    """Parse a quick expense message like "мийка 300" or "омивайка 150.50".

    Returns (title, amount) with the decimal comma normalized, or None when
    the message is not "<text> <positive amount>". A bare number does not
    match (it is treated as an odometer update instead).
    """
    match = _QUICK_EXPENSE_RE.fullmatch(text.strip())
    if match is None:
        return None
    title = match.group("title").strip()
    amount = float(match.group("amount").replace(",", "."))
    if not title or amount <= 0:
        return None
    return title, amount
