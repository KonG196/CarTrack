"""The OCR ladder: free rungs first, the vision model only when they fall short.

Three rungs ordered by price — tesseract (local), OCR.space (free, 25k/month),
Gemini (paid, and only if GEMINI_API_KEY is set). Reading a photo is separated
from judging it (`read_text`), so one climb can serve several parsers: the same
picture is offered to the receipt reader and the work-order reader without
paying for OCR twice.

Nothing here may break a request. Every rung fails soft — a remote error keeps
whatever the cheaper rung already read.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

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
from app.services.workorder import (
    ParsedWorkOrder,
    looks_like_work_order,
    parse_work_order,
)

logger = logging.getLogger(__name__)


class OcrUnavailable(Exception):
    """A configured vision model gave no answer (down / rate-limited / dead key).

    Distinct from a readable-but-empty photo: the receipt is fine, our OCR is
    temporarily unavailable. The scan endpoint turns this into a 503 so the app
    says «скан недоступний, спробуйте пізніше» instead of blaming the photo.
    """

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


def _ask_gemini(prompt: str, image_bytes: bytes, content_type: str) -> Optional[Any]:
    """Show the model one photo and one prompt; return the JSON it answers with.

    None on any failure — a caller keeps whatever the free rungs read. Nothing
    may break because someone else's API is having a day.
    """
    if not settings.GEMINI_API_KEY:
        return None
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
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
    # The key goes in a header, not a ?key= query param: keys are rejected in
    # the URL, and a header also keeps the key out of error messages and logs.
    for delay in (*_RETRY_DELAYS_SECONDS, None):
        response = httpx.post(
            _GEMINI_URL.format(model=settings.GEMINI_MODEL),
            headers={"x-goog-api-key": settings.GEMINI_API_KEY},
            json=payload,
            timeout=_TIMEOUT_SECONDS,
        )
        if response.status_code not in _RETRY_STATUSES or delay is None:
            break
        if _is_out_of_credit(response):
            break
        time.sleep(delay)

    # Three ways this ends badly, and only one of them is the model's fault.
    # «Fallback failed» in a log sends nobody to look at the billing page, so
    # the two that a human must fix say so plainly — and neither is worth a
    # retry, since both will be just as true next time.
    if response.status_code in (401, 403):
        logger.error(
            "GEMINI_API_KEY was rejected (HTTP %s). Vision OCR is off until it "
            "is replaced — get one at aistudio.google.com/apikey.",
            response.status_code,
        )
        return None
    if _is_out_of_credit(response):
        logger.error(
            "Gemini is out of credit, so vision OCR is off until the project is "
            "topped up (ai.studio/projects). The free rungs still read photos; "
            "this only costs the hardest ones."
        )
        return None
    response.raise_for_status()
    try:
        answer = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(answer)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None


#: A free-text intent parse must be quick — a bot user is waiting on the reply,
#: so give up fast and let the caller fall back rather than hang the chat.
_TEXT_TIMEOUT_SECONDS = 12.0


def ask_gemini_json_text(prompt: str) -> Optional[Any]:
    """Ask the model a text-only question; return the JSON it answers with.

    Same key / retry / quota handling as _ask_gemini but without an image — used
    to turn a free-text log message into a structured intent. None on any
    failure so the caller keeps its deterministic behaviour.
    """
    if not settings.GEMINI_API_KEY:
        return None
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
    }
    for delay in (*_RETRY_DELAYS_SECONDS, None):
        response = httpx.post(
            _GEMINI_URL.format(model=settings.GEMINI_MODEL),
            headers={"x-goog-api-key": settings.GEMINI_API_KEY},
            json=payload,
            timeout=_TEXT_TIMEOUT_SECONDS,
        )
        if response.status_code not in _RETRY_STATUSES or delay is None:
            break
        if _is_out_of_credit(response):
            break
        time.sleep(delay)
    if response.status_code != 200:
        return None
    try:
        answer = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(answer)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None


def _is_out_of_credit(response: httpx.Response) -> bool:
    """A 429 that will still be a 429 tomorrow.

    Rate limiting and a depleted balance share a status code, and only one of
    them is worth waiting out. A dead key retried three times is 90 seconds a
    user spends watching a loader for nothing.
    """
    if response.status_code != 429:
        return False
    try:
        message = response.json().get("error", {}).get("message", "")
    except ValueError:
        return False
    return "credit" in message.lower() or "billing" in message.lower()


def recognize_receipt_llm(
    image_bytes: bytes, content_type: str
) -> Optional[ParsedReceipt]:
    data = _ask_gemini(_PROMPT, image_bytes, content_type)
    return parsed_receipt_from_llm(data) if data is not None else None


def read_text(
    image_bytes: bytes,
    content_type: str,
    score: Callable[[str], int],
    enough: int,
    *,
    is_table: bool = False,
) -> str:
    """The best text the OCR rungs can produce, judged by the caller.

    Two rungs: tesseract, then OCR.space for the pixels tesseract could not
    read. Free and cardless, so nothing here costs money. What counts as a good
    read depends on the document, which only the caller knows — a receipt needs
    its numbers, an order needs its table — so the caller passes the judge and
    the threshold that stops the climb early.

    Separating the climb from the reading is what lets one photo be offered to
    several parsers without paying for OCR twice.
    """
    text = extract_text(image_bytes)
    if score(text) >= enough or not ocr_space.enabled():
        return text

    try:
        remote_text = ocr_space.recognize_text(image_bytes, content_type, is_table=is_table)
    except Exception:
        logger.warning("OCR.space fallback failed", exc_info=True)
        return text
    if not remote_text:
        return text

    # The text is what every wrong answer traces back to, and it is invisible
    # from the outside: a receipt read as «3.00 л × 13.99» instead of «43,06 л
    # × 15,99» looks like a parser bug until you see that the reader never saw
    # a 4.
    logger.info("OCR.space text:\n%s", remote_text)
    return remote_text if score(remote_text) > score(text) else text


def _receipt_score(text: str) -> int:
    return parse_receipt_text(text).found_in_text


def recognize_receipt(image_bytes: bytes, content_type: str = "image/jpeg") -> ParsedReceipt:
    """Read a receipt: the free rungs first, the vision model when they fall short.

    The single entry point for every caller. It used to live inline in the API
    router, so the bot — which runs OCR in-process — quietly had no fallback at
    all: a crumpled photo simply failed there while the web read it fine.

    A failure of the remote model keeps the local result: nothing may break
    because someone else's API is down.
    """
    if settings.GEMINI_API_KEY:
        # Vision-first. Measured on the prod CPU a single tesseract pass costs
        # ~27s and still reads NOTHING off a real phone photo, while the model
        # reads the same receipt in ~11s — so a tesseract pre-pass only added
        # latency. Go straight to the model.
        try:
            llm_parsed = recognize_receipt_llm(image_bytes, content_type)
        except Exception as exc:
            logger.warning("Vision OCR failed", exc_info=True)
            raise OcrUnavailable from exc
        if llm_parsed is not None:
            return llm_parsed
        # Model configured but gave no answer (down / rate-limited / dead key):
        # signal «temporarily unavailable» so the app can say «скан недоступний,
        # спробуйте пізніше» rather than «не вдалося розпізнати чек» — the photo
        # is fine, our OCR is not.
        raise OcrUnavailable

    # No vision model configured at all: the full free rungs are the only option.
    return parse_receipt_text(read_text(image_bytes, content_type, _receipt_score, 2))


def _score_of(parsed: ParsedWorkOrder) -> int:
    """How complete a reading of a service order this is, weighted by what for.

    Money, near enough: the items are a tiebreaker worth less than any one sum.
    Counting them heavily is what let a tesseract pass on a real invoice — one
    sum out of three, and twelve «items» that were the shop's phone number and
    the terminal window behind the paper — look like a complete read and stop
    the climb.
    """
    return (
        10 * (parsed.total_cost is not None)
        + 20 * (parsed.parts_cost is not None)
        + 20 * (parsed.labor_cost is not None)
        + min(len(parsed.items), 5)
    )


def _work_order_score(text: str) -> int:
    return _score_of(parse_work_order(text))


# All three sums. Anything less is worth one free call to a better reader — and
# an order that genuinely prints no split simply costs that call and keeps what
# it had.
_ORDER_ENOUGH = 50


_ORDER_PROMPT = """\
Це фото українського наряду-замовлення або рахунку-фактури зі СТО.
Поверни СУВОРО один JSON-обʼєкт без пояснень:
{"parts_cost": число або null, "labor_cost": число або null,
 "total_cost": число або null, "date": "YYYY-MM-DD" або null,
 "items": ["назва позиції", ...]}

- labor_cost — разом за роботи; parts_cost — разом за запчастини й матеріали;
  total_cost — сума до сплати.
- УВАГА: слово «Разом» може стояти двічі й означати різне — під заголовком
  «Вартість робіт» це роботи, під «Вартість придбаних товарів та матеріалів» —
  запчастини. Дивись, під яким заголовком стоїть сума.
- items — лише виконані роботи і встановлені запчастини. НЕ включай реквізити
  СТО, дані клієнта, авто, шапки таблиць і підсумкові рядки.
- Числа з десятковою крапкою. Не вигадуй: чого не видно — null.
"""


def parsed_work_order_from_llm(data: Any) -> Optional[ParsedWorkOrder]:
    """Map the model's JSON, believing none of it without checking.

    A vision model is a reader, not a source of truth: it will hand back a
    plausible number as readily as a real one, and this record is what the car
    is sold on.
    """
    if not isinstance(data, dict):
        return None

    def money(value: Any) -> Optional[float]:
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return None
        try:
            amount = float(str(value).replace(",", ".").strip())
        except ValueError:
            return None
        return amount if amount > 0 else None

    items = [
        str(item).strip()[:120]
        for item in (data.get("items") or [])
        if isinstance(item, (str, int, float)) and str(item).strip()
    ]
    result = ParsedWorkOrder(
        items=items,
        parts_cost=money(data.get("parts_cost")),
        labor_cost=money(data.get("labor_cost")),
        total_cost=money(data.get("total_cost")),
        date=_as_past_date_str(data.get("date")),
    )
    # The same arithmetic the text parser is held to. A model that read one of
    # the three wrong has no way to know it, so the split goes rather than the
    # user trusting a number that does not add up.
    if result.total_cost and result.parts_cost and result.labor_cost:
        drift = abs(result.parts_cost + result.labor_cost - result.total_cost)
        if drift > max(1.0, result.total_cost * 0.02):
            result.parts_cost = None
            result.labor_cost = None
    if result.total_cost is None and (result.parts_cost or result.labor_cost):
        result.total_cost = round((result.parts_cost or 0) + (result.labor_cost or 0), 2)
    return result


def _as_past_date_str(value: Any) -> Optional[str]:
    parsed = _as_past_date(value)
    return parsed.isoformat() if parsed else None


def recognize_work_order(
    image_bytes: bytes, content_type: str = "image/jpeg"
) -> ParsedWorkOrder:
    """Read a service order off a photo: the free rungs, then the model.

    The model is genuinely better at this — on a real invoice it read all eight
    line items to the regex parser's six, and cleanly. It still goes last and
    only when the free rungs came up short, because it is the only rung that
    costs money.
    """
    if settings.GEMINI_API_KEY:
        # Vision-first, same reasoning as receipts: a tesseract pass costs ~27s
        # on the prod CPU and reads a photographed наряд poorly, while the model
        # reads the table cleanly in ~11s. Go straight to the model.
        try:
            data = _ask_gemini(_ORDER_PROMPT, image_bytes, content_type)
        except Exception as exc:
            logger.warning("Vision OCR failed", exc_info=True)
            raise OcrUnavailable from exc
        if data is not None:
            llm_parsed = parsed_work_order_from_llm(data)
            if llm_parsed is not None:
                return llm_parsed
        # Model down/rate-limited/unparseable answer — signal «unavailable» so the
        # app says «спробуйте пізніше», not «не вдалося розпізнати».
        raise OcrUnavailable

    # No vision model configured at all: the full free rungs are the only option.
    return parse_work_order(
        read_text(image_bytes, content_type, _work_order_score, _ORDER_ENOUGH, is_table=True)
    )



@dataclass
class PhotoReading:
    """What a photo turned out to be, and what was read out of it."""

    kind: str  # "refuel" | "work_order" | "unreadable"
    receipt: ParsedReceipt
    work_order: ParsedWorkOrder


def _classify(text: str) -> PhotoReading:
    """Decide what a photo is by the evidence that is hardest to produce by accident.

    Neither parser refusing the other's document can be relied on. A fuel
    receipt is also a table of names and sums ending in «ДО СПЛАТИ», so it
    parses as a confident work order; and a real наряд reading «Олива моторна
    5W-30 5л» hands the receipt parser five litres, which it divides into the
    bill to price diesel at 1644 грн/л and calls two fields found.

    What does not happen by accident is the vocabulary: «наряд», «запчастини»,
    «н/год» are words no filling station prints. So a page that says them and
    parses as a complete order is one, whatever the receipt parser made of it.
    """
    receipt = parse_receipt_text(text)
    order = parse_work_order(text)
    if order.confident and looks_like_work_order(text):
        return PhotoReading("work_order", receipt, order)
    if receipt.found_in_text >= 2:
        return PhotoReading("refuel", receipt, order)
    return PhotoReading("unreadable", receipt, order)


def _photo_score(text: str) -> int:
    reading = _classify(text)
    if reading.kind == "refuel":
        return 50 + reading.receipt.found_in_text
    if reading.kind == "work_order":
        return _work_order_score(text)
    # Nothing readable yet, but a partial receipt still beats blank text: it is
    # what the next rung is compared against.
    return reading.receipt.found_in_text


def recognize_photo(image_bytes: bytes, content_type: str = "image/jpeg") -> PhotoReading:
    """Read a photo without being told what it is — a receipt or a service order.

    One climb up the rungs, both parsers on the text it returns, so a bot user
    photographs whatever paper the shop handed them and never picks a mode.

    The rung is asked for table layout: a receipt reads the same either way,
    while an order without it comes back a column at a time — every name, then
    every price — and no line holds both.
    """
    return _classify(
        read_text(image_bytes, content_type, _photo_score, _ORDER_ENOUGH, is_table=True)
    )
