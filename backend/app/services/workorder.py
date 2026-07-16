"""Parse a service-order photo into a maintenance entry.

A наряд-замовлення is a different animal from a fuel receipt: a table of five
to ten lines, each a part or an hour of labour, with a total at the bottom.
The fuel parser hunts for one triple (liters, price, total) and makes nonsense
of a table.

Shops print no two orders alike, so this reads structure rather than layout: a
line that names something and carries money is an item, and the word beside a
sum decides whether that sum is parts, labour or the bill.

Nothing here guesses silently. What it cannot read comes back None for the user
to fill, because a wrong service record is worse than an empty one — it becomes
the history the car is sold on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# Dates and percentages are digits that are not money. Stripped before any sum
# is read, or «Акт від 17.03.2023» bills the customer 2023 hryvnia.
_DATE_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b")
_PERCENT_RE = re.compile(r"\b\d{1,3}\s*%")

# Money as a shop prints it: «1 250,00», «3200.00», «681,38». The grouped form
# must come first and must group at least once, or the alternation settles for
# the first three digits of 8223,38.
_MONEY = r"\d{1,3}(?:[  ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_MONEY_RE = re.compile(_MONEY)

_TOTAL_KEYWORDS = ("до сплати", "разом", "всього", "усього", "загалом", "сума наряду")
_PARTS_KEYWORDS = ("запчастин", "деталі", "матеріали", "товари")
_LABOR_KEYWORDS = ("робот", "робіт", "послуг", "н/год", "нормо")
_VAT_KEYWORDS = ("пдв", "податок")
_SUMMARY_KEYWORDS = _TOTAL_KEYWORDS + _PARTS_KEYWORDS + _LABOR_KEYWORDS + _VAT_KEYWORDS

# A subtotal, never the bill.
_NET_OF_VAT = ("без пдв", "без податк")

# Lines that are never work: headers, the shop's paperwork, the customer, the car.
_NOISE = (
    "наряд",
    "замовлення",
    "акт",
    "рахунок",
    "клієнт",
    "замовник",
    "виконавець",
    "автомобіль",
    "пробіг",
    "vin",
    "держ",
    "дата",
    "підпис",
    "печатка",
    "директор",
    "майстер",
    "тел.",
    "адреса",
    "єдрпоу",
    "п/п",
    "найменування",
    "кільк",
)

_MIN_ITEM_NAME = 4
_MAX_SUMMARY_WORDS = 3

# Words a shop prints and a filling station does not. A fuel receipt is also a
# table of names and sums with «ДО СПЛАТИ» at the foot, so it parses as a
# perfectly confident work order — these are what tell the two apart.
#
# Deliberately not «замовлення» on its own: the café at a WOG station prints it
# over a coffee order, and that would turn a fuel receipt into a service record.
# «Наряд-замовлення» is still caught by «наряд».
_ORDER_MARKERS = (
    "наряд",
    "акт виконаних",
    "виконані роботи",
    "запчастин",
    "автосервіс",
    "н/год",
    "нормо",
)


def looks_like_work_order(text: str) -> bool:
    """Whether this text is a service order rather than something else that parses like one."""
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _ORDER_MARKERS)


@dataclass
class ParsedWorkOrder:
    items: list[str] = field(default_factory=list)
    parts_cost: Optional[float] = None
    labor_cost: Optional[float] = None
    total_cost: Optional[float] = None
    date: Optional[str] = None
    # Everything the reader saw, so a wrong answer can be diagnosed from the
    # response instead of the server logs.
    raw_text: str = ""

    @property
    def confident(self) -> bool:
        """Whether this is worth offering as a filled-in card at all."""
        return bool(self.items) and self.total_cost is not None


def _to_float(raw: str) -> Optional[float]:
    cleaned = raw.replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if value > 0 else None


def _without_non_money(line: str) -> str:
    return _PERCENT_RE.sub(" ", _DATE_RE.sub(" ", line))


def _money_on(line: str) -> list[float]:
    found = _MONEY_RE.findall(_without_non_money(line))
    return [value for value in (_to_float(raw) for raw in found) if value]


def _words_besides_numbers(line: str) -> list[str]:
    text = _MONEY_RE.sub(" ", _without_non_money(line))
    return re.sub(r"[^\w\s]", " ", text).split()


def _is_noise(lowered: str) -> bool:
    return any(word in lowered for word in _NOISE)


def _is_summary_line(line: str) -> bool:
    """A totals row: a keyword, a sum, and nothing else worth naming.

    The word count is what separates «Роботи: 681,38» from the item «Роботи по
    заміні ГРМ» — one is the labour total, the other is labour.
    """
    lowered = line.lower()
    if not any(word in lowered for word in _SUMMARY_KEYWORDS):
        return False
    return len(_words_besides_numbers(line)) <= _MAX_SUMMARY_WORDS


def _clean_item_name(line: str) -> str:
    """«3  Фільтр масляний ЦБ012317  1  566,00  566,00» -> «Фільтр масляний ЦБ012317»."""
    without_lead = re.sub(r"^\s*\d{1,2}[.)]?\s+", "", line)
    without_trail = re.sub(rf"(?:\s+(?:{_MONEY}|[xх×*]|шт\.?|компл\.?))+\s*$", "", without_lead)
    return re.sub(r"\s{2,}", " ", without_trail).strip(" .-—:;")


def _keyword_amount(lines: list[str], keywords: tuple[str, ...]) -> Optional[float]:
    """The largest sum on the lowest line naming this keyword.

    Lowest, because totals live at the foot of the page while the same word may
    head the table — and because a shop that prints «Разом без ПДВ», «ПДВ» and
    «Всього до сплати» prints them in that order, so reading upward finds the
    bill before it finds the subtotal.

    Largest, because such a line often carries the sum twice, with and without
    tax, and the customer pays the bigger one.
    """
    for line in reversed(lines):
        lowered = line.lower()
        if not any(word in lowered for word in keywords):
            continue
        if any(word in lowered for word in _NET_OF_VAT):
            continue
        amounts = _money_on(line)
        if amounts:
            return max(amounts)
    return None


def parse_work_order(text: str) -> ParsedWorkOrder:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    result = ParsedWorkOrder(raw_text=text or "")
    if not lines:
        return result

    result.parts_cost = _keyword_amount(lines, _PARTS_KEYWORDS)
    result.labor_cost = _keyword_amount(lines, _LABOR_KEYWORDS)
    result.total_cost = _keyword_amount(lines, _TOTAL_KEYWORDS)

    for line in lines:
        if _is_noise(line.lower()) or _is_summary_line(line):
            continue
        # An item names something and costs something. Without money it is a
        # note; without letters it is a column of figures.
        if not _money_on(line):
            continue
        name = _clean_item_name(line)
        if len(name) < _MIN_ITEM_NAME or not re.search(r"[a-zA-Zа-яА-ЯіїєґІЇЄҐ]{3}", name):
            continue
        if name not in result.items:
            result.items.append(name)

    # A bill nobody printed can still be added up, but only from halves that
    # were: summing the item rows would double-count a labour row that also
    # names the part it went into.
    if result.total_cost is None and (result.parts_cost or result.labor_cost):
        result.total_cost = round((result.parts_cost or 0) + (result.labor_cost or 0), 2)

    # The split is worth keeping only if it agrees with the bill. When it does
    # not, one of the three was misread and there is no telling which, so the
    # user retypes two numbers instead of trusting a wrong one.
    if result.total_cost and result.parts_cost and result.labor_cost:
        drift = abs(result.parts_cost + result.labor_cost - result.total_cost)
        if drift > max(1.0, result.total_cost * 0.02):
            result.parts_cost = None
            result.labor_cost = None

    match = _DATE_RE.search(text or "")
    if match:
        parts = re.split(r"[./-]", match.group())
        day, month, year = (int(part) for part in parts)
        if 1 <= day <= 31 and 1 <= month <= 12 and year > 1900:
            result.date = f"{year:04d}-{month:02d}-{day:02d}"

    return result
