"""Parse a service order or an invoice photo into a maintenance entry.

A наряд is a different animal from a fuel receipt: a table of parts and hours
with a total at the foot. The fuel parser hunts for one triple (litres, price,
total) and makes nonsense of a table.

Shops print no two alike, so this reads **sections**, not layout. That is the
whole design, and it comes from a real invoice: a рахунок-фактура prints
«Вартість робіт», a table, «Разом: 16 000,00» — then «Вартість придбаних
товарів та матеріалів», another table, «Разом: 3 200,00». The same word,
«Разом», means labour once and parts once. Only the heading above it says
which, so the heading is what this tracks.

Two more things that real paper does and invented fixtures never did:
the sum can be printed **above** its label rather than beside it, and OCR reads
«3 200,00» as «З 200,00» — a Cyrillic З where a three should be.

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
_MONEY = r"\d{1,3}(?:[  ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_MONEY_RE = re.compile(_MONEY)

# Letters an OCR pass puts where digits belong. Applied only where the whole
# line is expected to be a number, so a word can never be folded into one.
_DIGIT_LOOKALIKES = str.maketrans({"З": "3", "з": "3", "О": "0", "о": "0", "б": "6", "І": "1", "і": "1"})
_NUMERIC_LINE_RE = re.compile(r"[\d\s., ]+")

_TOTAL_KEYWORDS = ("до сплати", "разом", "всього", "усього", "загалом", "загальна сума")
# Stems, not words: a shop writes «матеріалів» and «товарів» in the genitive,
# and «матеріали» matches neither.
_PARTS_KEYWORDS = ("запчастин", "деталей", "деталі", "матеріал", "товар")
_LABOR_KEYWORDS = ("робот", "робіт", "послуг", "н/год", "нормо")
_VAT_KEYWORDS = ("пдв", "податок")

# A subtotal, never the bill.
_NET_OF_VAT = ("без пдв", "без податк")

# Headings that open a priced section. What follows belongs to that section
# until it is totalled.
_LABOR_SECTION = ("вартість робіт", "вартість роботи", "виконані роботи", "перелік робіт")
_PARTS_SECTION = (
    "вартість придбаних",
    "товарів та матеріалів",
    "запчастини та матеріали",
    "використані матеріали",
)

# Lines that are never work: the shop's letterhead, its banking, the customer,
# the car, and the table's own column headings.
_NOISE = (
    "наряд",
    "замовлення",
    "акт",
    "рахунок",
    "фактура",
    "клієнт",
    "замовник",
    "виконавець",
    "автомобіль",
    "пробіг",
    "vin",
    "держ",
    "марка та модель",
    "тип тз",
    "рік випуску",
    "двигун",
    "дата",
    "підпис",
    "підлис",
    "прізвище",
    "ініціали",
    "печатка",
    "директор",
    "майстер",
    "телефон",
    "тел.",
    "email",
    "@",
    "адреса",
    "місцезнаходження",
    "єдрпоу",
    "iban",
    "розрахунок",
    "безготівков",
    "платником",
    "п/п",
    "пп",
    "найменування",
    "кільк",
    "к-сть",
    "од. вим",
    "од.вим",
    "ціна",
    "сума",
    "бренд",
    "номер запчастини",
)

# «Од. вим.» values: what the shop charges by, never what it did.
_UNIT_RE = re.compile(r"фікс\.?\s*варт\.?|н/год|нормо-?год", re.IGNORECASE)

_MIN_ITEM_NAME = 4
_MAX_SUMMARY_WORDS = 4

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
    "вартість робіт",
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
        """Whether this is worth offering as a filled-in card at all.

        The bill alone is not enough. A photo that yields a total and nothing
        else is usually one the reader half-failed on, and offering it as a
        filled card invites the user to save a number with no work attached to
        it — so the split or the items have to back it up.
        """
        if self.total_cost is None:
            return False
        return bool(self.items) or self.parts_cost is not None or self.labor_cost is not None


def _to_float(raw: str) -> Optional[float]:
    cleaned = raw.replace(" ", "").replace(" ", "").replace(",", ".")
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


def _amount_if_numeric_line(line: str) -> Optional[float]:
    """The sum on a line that is nothing but a sum.

    Used to pair «Разом:» with the «16 000,00» printed above it. The line must
    be numeric through and through — otherwise a label could steal the price
    out of the item row next to it.
    """
    folded = _without_non_money(line).translate(_DIGIT_LOOKALIKES).strip()
    if not folded or not _NUMERIC_LINE_RE.fullmatch(folded):
        return None
    amounts = _money_on(folded)
    return max(amounts) if amounts else None


def _words_besides_numbers(line: str) -> list[str]:
    text = _MONEY_RE.sub(" ", _without_non_money(line))
    return re.sub(r"[^\w\s]", " ", text).split()


def _is_noise(lowered: str) -> bool:
    return any(word in lowered for word in _NOISE)


def _has_any(lowered: str, keywords: tuple[str, ...]) -> bool:
    return any(word in lowered for word in keywords)


def _is_summary_line(line: str) -> bool:
    """A totals row: a keyword, maybe a sum, and nothing else worth naming."""
    lowered = line.lower()
    if not _has_any(lowered, _TOTAL_KEYWORDS + _PARTS_KEYWORDS + _LABOR_KEYWORDS + _VAT_KEYWORDS):
        return False
    return len(_words_besides_numbers(line)) <= _MAX_SUMMARY_WORDS


def _clean_item_name(line: str) -> str:
    """«3  Фільтр масляний ЦБ012317  1  566,00  566,00» -> «Фільтр масляний ЦБ012317»."""
    flat = re.sub(r"\s+", " ", line).strip()
    # The unit column sits between the name and the price, so it is cut out
    # rather than trimmed off an end. Dropping the whole row for containing it
    # would cost «Діагностика | фікс. варт. | 1 | 2 000,00» — a real line item.
    without_unit = _UNIT_RE.sub(" ", flat)
    without_lead = re.sub(r"^\s*\d{1,2}[.)]?\s+", "", without_unit)
    without_trail = re.sub(
        rf"(?:\s+(?:{_MONEY}|[xх×*]|шт\.?|компл\.?))+\s*$", "", without_lead
    )
    return re.sub(r"\s{2,}", " ", without_trail).strip(" .-—:;|")


def _section_of(lowered: str) -> Optional[str]:
    if _has_any(lowered, _LABOR_SECTION):
        return "labor"
    if _has_any(lowered, _PARTS_SECTION):
        return "parts"
    return None


def _bucket_of(lowered: str, section: Optional[str]) -> Optional[str]:
    """Which figure a totals line is stating.

    An explicit word wins: «Запчастини: 7542,00» is parts wherever it stands.
    A bare «Разом:» has no word to go on, so it means whichever section it
    closes — and if it closes none, it is the bill.
    """
    if _has_any(lowered, _NET_OF_VAT) or _has_any(lowered, _VAT_KEYWORDS):
        if not _has_any(lowered, _TOTAL_KEYWORDS):
            return None
        if _has_any(lowered, _NET_OF_VAT):
            return None
    if _has_any(lowered, _PARTS_KEYWORDS):
        return "parts"
    if _has_any(lowered, _LABOR_KEYWORDS):
        return "labor"
    if not _has_any(lowered, _TOTAL_KEYWORDS):
        return None
    return section or "total"


def _amount_for(lines: list[str], index: int) -> Optional[float]:
    """The sum belonging to the label on this line.

    Beside it, else above it, else below it: OCR of a table puts the figure on
    its own line as often as not, and which side it lands on is the engine's
    business, not the shop's.

    Only a totalling word may reach for a neighbour. «Разом:» genuinely prints
    alone with its figure above; «Запчастини: 7542,00» always carries its own.
    So a bare «запчастини» is the «Номер запчастини» column heading, and
    letting it borrow the number beside it invents a subtotal out of a price.
    """
    amounts = _money_on(lines[index])
    if amounts:
        return max(amounts)
    if not _has_any(lines[index].lower(), _TOTAL_KEYWORDS):
        return None
    for neighbour in (index - 1, index + 1):
        if 0 <= neighbour < len(lines):
            amount = _amount_if_numeric_line(lines[neighbour])
            if amount is not None:
                return amount
    return None


def _walk(lines: list[str]) -> tuple[dict[str, float], list[int]]:
    """Read the page top to bottom once, returning its sums and its priced rows.

    One pass, because the two answers are the same question: which section a
    line sits in decides both what a «Разом:» is totalling and whether a line
    is work at all.
    """
    found: dict[str, float] = {}
    in_section: list[int] = []
    section: Optional[str] = None

    for index, line in enumerate(lines):
        lowered = line.lower()
        # The letterhead and the column headings are not sums. «№ пп |
        # Найменування роботи | 6 000,00» is a heading that OCR glued a figure
        # onto — read as a labour total it both invents one and closes the
        # section, so the «Разом:» that really was the labour total no longer
        # knows which section it ends.
        if _is_noise(lowered):
            continue

        heading = _section_of(lowered)
        # A heading names a section only when it is a heading — «Вартість
        # робіт» over a table, not a row that happens to say «робіт».
        if heading and not _money_on(line):
            section = heading
            continue

        if _is_summary_line(line):
            bucket = _bucket_of(lowered, section)
            amount = _amount_for(lines, index) if bucket else None
            if bucket and amount is not None:
                # Top to bottom, so a later line overwrites an earlier one:
                # «Всього» at the foot outranks anything above it.
                found[bucket] = amount
                if bucket in ("parts", "labor"):
                    # The section is closed by its own total; «Всього» further
                    # down belongs to no section and must not inherit this one.
                    section = None
                continue

        if section is not None:
            in_section.append(index)

    return found, in_section


def _read_items(lines: list[str], in_section: list[int]) -> list[str]:
    """The rows that are work.

    Scoped to the priced sections when the page has any. That is what keeps a
    photographed invoice from logging the room it was photographed in: on the
    real one, a laptop behind the paper put «164 files changed, 9921
    insertions(+)» through OCR, and it reads as a line that names something and
    carries a number — which is the whole of the test outside a section.
    """
    candidates = in_section or range(len(lines))
    items: list[str] = []
    for index in candidates:
        line = lines[index]
        if _is_noise(line.lower()) or _is_summary_line(line):
            continue
        # An item names something and costs something. Without money it is a
        # note; without letters it is a column of figures.
        if not _money_on(line):
            continue
        name = _clean_item_name(line)
        if len(name) < _MIN_ITEM_NAME or not re.search(r"[a-zA-Zа-яА-ЯіїєґІЇЄҐ]{3}", name):
            continue
        if name not in items:
            items.append(name)
    return items


def parse_work_order(text: str) -> ParsedWorkOrder:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    result = ParsedWorkOrder(raw_text=text or "")
    if not lines:
        return result

    money, in_section = _walk(lines)
    result.parts_cost = money.get("parts")
    result.labor_cost = money.get("labor")
    result.total_cost = money.get("total")
    result.items = _read_items(lines, in_section)

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
