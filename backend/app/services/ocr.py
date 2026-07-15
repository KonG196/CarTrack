"""Receipt OCR: image -> raw text (tesseract) and raw text -> refuel fields."""

from __future__ import annotations

import datetime as dt
import io
import re
from dataclasses import dataclass
from typing import Optional

import pytesseract
from PIL import Image, ImageFilter, ImageOps

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

# Keywords marking the receipt total, in priority order: «плат» catches the
# card-payment line (ФОРМА ОПЛАТИ: ПЛАТ. КАРТ) and, with «сплачено», goes
# after the true total keywords because a payment may exceed the actual total
# (cash + change) or be one part of a split payment.
TOTAL_KEYWORDS: tuple[str, ...] = (
    "до сплати",
    "сума",
    "разом",
    "total",
    "плат",
    "еквайринг",
    "сплачено",
)

# Tesseract renders Cyrillic letters as Latin lookalikes on noisy photos
# («СУМА» -> "CYMA", «КАРТ» -> "KAPT"); fold them back before keyword search.
_LOOKALIKE_MAP = str.maketrans("abcehikmoptxy", "авсенікмортху")

# The paid total sits at or below liters * price (fuel discounts exist, but
# not 50% ones), so a candidate outside this band is an OCR digit misread.
_TOTAL_MIN_RATIO = 0.5
_TOTAL_MAX_RATIO = 1.02

# Sanity cap for a single refuel: even a truck tank stays a few hundred
# liters, so anything above this is an OCR misread (serial numbers, coupons).
MAX_LITERS = 200.0

# Plausible unit-price band, UAH per liter. Receipts also print per-liter
# tax and discount rates ("складає 4.36 грн/л", "0.3 грн/л") — those sit
# below any real fuel price.
MIN_PRICE_PER_LITER = 5.0
MAX_PRICE_PER_LITER = 150.0

# No real refuel costs less than this; a smaller "total" is a stray digit
# picked up from a garbled line.
MIN_TOTAL = 20.0

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
# Fiscal printers put the dispensing line as "40,45 X 19,99" (quantity times
# unit price) with no liters marker at all; the separator OCRs as a Latin or
# Cyrillic x, "×" or "*". Between the quantity and the separator there may be
# a units marker or its misread ("64,84 л х 26,49", "54.84 a x 26,49") —
# allow up to two letters there.
_QTY_X_PRICE_RE = re.compile(
    rf"(?<![\d.,/])({_NUMBER})[ \t]*(?:[^\W\d_]{{1,2}}[ \t]+)?[xх×*][ \t]*({_NUMBER})",
    re.IGNORECASE,
)
# A money amount ("1717,61"). No trailing boundary on purpose: OCR glues
# stray glyphs to amounts ("808,604" for "808,60А") and the fragment before
# the extra digit is still the amount.
_MONEY_RE = re.compile(r"\d+[.,]\d{2}")
# Marks the line naming the dispensed fuel; that line also carries the gross
# amount (liters * unit price) on fiscal receipts.
_FUEL_LINE_RE = re.compile(r"бензин|дизел|паливо|газ|а-9\d|а-80|євро", re.IGNORECASE)
# OCR splits amounts around the decimal separator ("808 ,60", "20, 00");
# closing those gaps restores the money token.
_NUM_GAP_BEFORE_SEP_RE = re.compile(r"(?<=\d)[ \t]+(?=[.,]\d)")
_NUM_GAP_AFTER_SEP_RE = re.compile(r"(?<=\d[.,])[ \t]+(?=\d)")
_DATE_RE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b")
# Fiscal printers also stamp dd-mm-yy ("ДАТА: 15-01-16"); tried only when no
# four-digit-year date is present.
_SHORT_DATE_RE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2})\b")


@dataclass
class ParsedReceipt:
    """Structured fields recognized on a fuel receipt (None when not found)."""

    liters: Optional[float] = None
    price_per_liter: Optional[float] = None
    total_cost: Optional[float] = None
    date: Optional[dt.date] = None
    gas_station: Optional[str] = None
    # How many of liters/price/total were read from the text rather than
    # derived from the other two; multi-pass OCR uses it to rank passes.
    found_in_text: int = 0


# Below this size (min dimension, px) a receipt photo is a thumbnail whose
# glyphs are only a few pixels tall; tesseract needs it upscaled first.
_SMALL_IMAGE_PX = 1500


def _ocr(image: Image.Image, psm: int) -> str:
    """One tesseract pass; falls back to English-only when "ukr" traineddata
    is missing (pytesseract raises TesseractError for it)."""
    try:
        return pytesseract.image_to_string(
            image, lang="ukr+eng", config=f"--psm {psm}"
        )
    except pytesseract.TesseractError:
        return pytesseract.image_to_string(image, lang="eng", config=f"--psm {psm}")


def _parse_score(text: str) -> int:
    """How much refuel data a pass recovered; money fields weigh double.

    Only fields actually read from the text count — a value derived from
    the other two is no evidence of OCR quality, and a garbage pass must
    not win (or stop the retries) on manufactured numbers.
    """
    parsed = parse_receipt_text(text)
    extra = (parsed.date, parsed.gas_station)
    return 2 * parsed.found_in_text + sum(v is not None for v in extra)


def extract_text(image_bytes: bytes) -> str:
    """OCR an image with tesseract, preferring Ukrainian + English.

    The image is grayscaled and tesseract runs with --psm 6 ("one uniform
    text block"): a receipt is a single narrow column, and the default auto
    segmentation shreds the dispensing line ("40,45 X 19,99") into separate
    fragments on phone photos.

    When that pass misses any money field, more passes run (upscaled and
    denoised variants for small images) and the pass whose text parses into
    the most refuel fields wins. TesseractNotFoundError — the tesseract
    binary itself is absent — propagates to the caller.
    """
    image = ImageOps.grayscale(Image.open(io.BytesIO(image_bytes)))
    best_text = _ocr(image, psm=6)
    best_score = _parse_score(best_text)
    if best_score >= 6:  # liters, price and total all recognized
        return best_text

    if min(image.size) < _SMALL_IMAGE_PX:
        up4 = image.resize((image.width * 4, image.height * 4), Image.LANCZOS)
        up3 = image.resize((image.width * 3, image.height * 3), Image.LANCZOS)
        retries = [
            (ImageOps.autocontrast(up4.filter(ImageFilter.MedianFilter(3)), cutoff=2), 6),
            (ImageOps.autocontrast(up3, cutoff=2), 4),
        ]
    else:
        retries = [(image, 4)]
    for variant, psm in retries:
        text = _ocr(variant, psm=psm)
        score = _parse_score(text)
        if score > best_score:
            best_text, best_score = text, score
            if best_score >= 6:
                break
    return best_text


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


def _plausible_price(value: float) -> Optional[float]:
    return value if MIN_PRICE_PER_LITER <= value <= MAX_PRICE_PER_LITER else None


def _parse_price_per_liter(text: str) -> Optional[float]:
    match = _PRICE_PER_LITER_RE.search(text)
    if match:
        return _plausible_price(_to_float(match.group(1)))
    for line in text.splitlines():
        if _PRICE_LABEL_RE.search(_fold_lookalikes(line.lower())):
            numbers = _NUMBER_RE.findall(line)
            if numbers:
                return _plausible_price(_to_float(numbers[0]))
    return None


def _parse_qty_x_price(text: str) -> tuple[Optional[float], Optional[float]]:
    """Find the fuel dispensing line written as "quantity X unit-price".

    Shop items print the same shape ("Кава 2 x 35,00"), so this is only a
    fallback for receipts without an explicit liters marker; the sanity cap
    filters coupon/serial lines that happen to contain an "x".
    """
    for match in _QTY_X_PRICE_RE.finditer(text):
        qty = _to_float(match.group(1))
        price = _to_float(match.group(2))
        if 0 < qty <= MAX_LITERS and price > 0:
            return qty, price
    return None, None


def _fold_lookalikes(lowered: str) -> str:
    """Fold Latin lookalike letters in a lowercased string back to Cyrillic."""
    return lowered.translate(_LOOKALIKE_MAP)


def _fix_number_gaps(text: str) -> str:
    """Close OCR gaps around decimal separators ("808 ,60" -> "808,60")."""
    return _NUM_GAP_AFTER_SEP_RE.sub("", _NUM_GAP_BEFORE_SEP_RE.sub("", text))


def _appears(value: float, gap_fixed_text: str) -> bool:
    """Check that an amount is printed in the text (with either separator)."""
    dotted = f"{value:.2f}"
    return dotted in gap_fixed_text or dotted.replace(".", ",") in gap_fixed_text


def _parse_fuel_line_gross(gap_fixed_text: str) -> Optional[float]:
    """The gross amount (liters * unit price) printed on the fuel-name line.

    The largest money token wins: the fuel line may also carry grade digits
    ("А-95") and stray OCR glyphs, but the amount dominates any of those.
    """
    for line in gap_fixed_text.splitlines():
        if _FUEL_LINE_RE.search(_fold_lookalikes(line.lower())):
            amounts = [_to_float(raw) for raw in _MONEY_RE.findall(line)]
            if amounts:
                return max(amounts)
    return None


def _repair_liters(
    liters: Optional[float],
    price: Optional[float],
    gross: Optional[float],
    gap_fixed_text: str,
) -> Optional[float]:
    """Cross-check liters against the fuel-line gross and fix a misread.

    liters * price is always printed on a fiscal receipt. When the parsed
    quantity times the price appears nowhere in the text, but the fuel-line
    amount divides by the price cleanly into a two-decimal quantity, the
    quantity token was the misread ("54.84" for 64,84) — take gross / price.
    """
    if price is None or gross is None:
        return liters
    if liters is not None and _appears(round(liters * price, 2), gap_fixed_text):
        return liters
    candidate = round(gross / price, 2)
    if abs(candidate * price - gross) < 0.01 and 0 < candidate <= MAX_LITERS:
        return candidate
    return liters


def _find_unanchored_total(
    gross: float, gap_fixed_text: str
) -> Optional[float]:
    """Recover the paid total when every total keyword got garbled by OCR.

    Scans all money tokens for values sitting in the discount band below
    liters * price. The gross itself is excluded; if the total equals the
    gross (no discount), _fill_missing_third reconstructs it anyway. Prefers
    the most repeated value (receipts print the paid amount several times),
    then the one closest to the gross.
    """
    amounts = [_to_float(raw) for raw in _MONEY_RE.findall(gap_fixed_text)]
    in_band = [
        value
        for value in amounts
        if _TOTAL_MIN_RATIO * gross <= value <= _TOTAL_MAX_RATIO * gross
        and abs(value - gross) > 0.011
        and value >= MIN_TOTAL
    ]
    if not in_band:
        return None
    return max(in_band, key=lambda v: (in_band.count(v), -abs(v - gross)))


def _iter_total_candidates(text: str):
    """Yield (priority tier, value) for every number on a total-keyword line."""
    for tier, keyword in enumerate(TOTAL_KEYWORDS):
        for line in text.splitlines():
            lowered = line.lower()
            folded = _fold_lookalikes(lowered)
            if keyword not in lowered and keyword not in folded:
                continue
            # Tax-summary lines reuse the total vocabulary («ПЛАТИМО
            # ПОДАТКИ РАЗОМ», "сплачено 187.82 грн податків") but their
            # amounts are taxes, not the receipt total.
            if "податк" in folded:
                continue
            # OCR may merge the price line into the total line: drop
            # per-liter price tokens ("54.99 ГРН/Л") so they cannot be
            # mistaken for the amount paid.
            cleaned = _PRICE_PER_LITER_RE.sub(" ", line)
            for raw in _NUMBER_RE.findall(cleaned):
                value = _to_float(raw)
                if value >= MIN_TOTAL:
                    yield tier, value


def _parse_total(
    text: str,
    liters: Optional[float] = None,
    price_per_liter: Optional[float] = None,
) -> Optional[float]:
    candidates = list(_iter_total_candidates(text))
    if not candidates:
        return None
    # When the dispensing line gave us liters and unit price, they anchor the
    # total: a keyword-line value far from liters * price is a digit misread
    # ("755,96" OCR'd as "155,96"), so prefer the closest in-band candidate
    # regardless of keyword priority.
    if liters and price_per_liter:
        gross = liters * price_per_liter
        consistent = [
            value
            for _, value in candidates
            if _TOTAL_MIN_RATIO * gross <= value <= _TOTAL_MAX_RATIO * gross
        ]
        if consistent:
            return min(consistent, key=lambda value: abs(value - gross))
    for tier, _ in enumerate(TOTAL_KEYWORDS):
        tier_values = [value for t, value in candidates if t == tier]
        if tier_values:
            # Prefer the largest money-looking value on the total line(s):
            # smaller numbers there are usually VAT or quantities.
            return max(tier_values)
    return None


def _parse_date(text: str) -> Optional[dt.date]:
    for match in _DATE_RE.finditer(text):
        day, month, year = (int(part) for part in match.groups())
        try:
            return dt.date(year, month, day)
        except ValueError:
            continue
    for match in _SHORT_DATE_RE.finditer(text):
        day, month, year = (int(part) for part in match.groups())
        try:
            candidate = dt.date(2000 + year, month, day)
        except ValueError:
            continue
        # A refuel receipt cannot be from the future: such a match is two
        # stray numbers, not a date.
        if candidate <= dt.date.today():
            return candidate
    return None


def _parse_gas_station(text: str) -> Optional[str]:
    lowered = text.lower()
    folded = _fold_lookalikes(lowered)
    for canonical, spellings in GAS_STATION_BRANDS:
        for spelling in spellings:
            if re.search(rf"\b{re.escape(spelling)}", lowered) or re.search(
                rf"\b{re.escape(spelling)}", folded
            ):
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

    Pure function (no I/O): recognizes liters ("45.50 Л" or the fiscal
    "40,45 X 19,99" quantity-times-price line), the total
    (СУМА / ДО СПЛАТИ / РАЗОМ / TOTAL / СПЛАЧЕНО lines), the price per liter
    (ЦІНА / грн-per-liter markers), a dd.mm.yyyy-style date and known gas
    station brands. Decimal commas are normalized to dots and the missing
    third of (liters, price, total) is derived when exactly two are found.
    """
    liters = _parse_liters(text)
    qty, unit_price = _parse_qty_x_price(text)
    if liters is None:
        # No explicit liters marker anywhere: fall back to the fiscal-style
        # "quantity X price" dispensing line.
        liters = qty
    price_per_liter = None
    if liters is not None and qty is not None and abs(qty - liters) < 0.01:
        # The X-line quantity matches the liters, so it is the fuel line
        # (not a shop item) and its second number is the unit price. It
        # outranks any "грн/л" token: tax-info lines quote per-liter tax
        # rates with the same wording, and deriving the price from the
        # total instead would bake any discount into it.
        price_per_liter = unit_price
    if price_per_liter is None:
        price_per_liter = _parse_price_per_liter(text)

    gap_fixed = _fix_number_gaps(text)
    gross = _parse_fuel_line_gross(gap_fixed)
    liters = _repair_liters(liters, price_per_liter, gross, gap_fixed)

    total = _parse_total(text, liters, price_per_liter)
    if total is None and liters and price_per_liter:
        total = _find_unanchored_total(liters * price_per_liter, gap_fixed)

    result = ParsedReceipt(
        liters=liters,
        price_per_liter=price_per_liter,
        total_cost=total,
        date=_parse_date(text),
        gas_station=_parse_gas_station(text),
        found_in_text=sum(
            value is not None for value in (liters, price_per_liter, total)
        ),
    )
    _fill_missing_third(result)
    return result
