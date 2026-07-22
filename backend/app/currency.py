"""Per-user display currency.

Kapot Tracker stores money as plain numbers with NO conversion — a user's
currency choice only decides which symbol is shown, never the value. So this is
a display preference, like the language. USD is the default for new accounts;
rows that predate the column keep UAH (their amounts were entered as hryvnia).

The list is ordered by popularity, with UAH second (this app's home currency).
Keep it in sync with the frontend `src/currency.js`.
"""

from __future__ import annotations

# code -> (symbol, prefix?) — prefix means the symbol goes before the number
# ("$1,250"); otherwise after it ("1 250 ₴").
CURRENCIES: dict[str, tuple[str, bool]] = {
    "USD": ("$", True),
    "UAH": ("₴", False),
    "EUR": ("€", True),
    "GBP": ("£", True),
    "PLN": ("zł", False),
    "CZK": ("Kč", False),
    "CAD": ("C$", True),
    "AUD": ("A$", True),
    "CHF": ("Fr", False),
    "JPY": ("¥", True),
}

DEFAULT_CURRENCY = "USD"
CURRENCY_CODES: tuple[str, ...] = tuple(CURRENCIES.keys())


def normalize_currency(value: str | None, default: str = DEFAULT_CURRENCY) -> str:
    """Coerce any input to a supported currency code, else the default."""
    if not value:
        return default
    code = str(value).strip().upper()
    return code if code in CURRENCIES else default


def currency_symbol(code: str | None) -> str:
    return CURRENCIES.get(normalize_currency(code), CURRENCIES[DEFAULT_CURRENCY])[0]


def currency_is_prefix(code: str | None) -> bool:
    return CURRENCIES.get(normalize_currency(code), CURRENCIES[DEFAULT_CURRENCY])[1]


def format_money(amount, code: str | None, *, decimals: int = 2, grouped: bool = True) -> str:
    """Backend money formatter: '$1,250.50' / '1 250,50 ₴' by the currency's rules.

    Groups thousands with a thin space and uses a comma decimal for suffix
    (European-style) currencies; a comma group and dot decimal for prefix ones.
    """
    code = normalize_currency(code)
    symbol, prefix = CURRENCIES[code]
    value = float(amount or 0)
    sign = "-" if value < 0 else ""
    fixed = f"{abs(value):.{decimals}f}"
    int_part, _, frac = fixed.partition(".")
    if grouped:
        int_part = _group(int_part, thousands="," if prefix else " ")
    dec_sep = "." if prefix else ","
    body = int_part if (decimals == 0 or frac == "0" * decimals) else f"{int_part}{dec_sep}{frac}"
    return f"{sign}{symbol}{body}" if prefix else f"{sign}{body} {symbol}"


def _group(digits: str, thousands: str) -> str:
    out = []
    for i, ch in enumerate(reversed(digits)):
        if i and i % 3 == 0:
            out.append(thousands)
        out.append(ch)
    return "".join(reversed(out))
