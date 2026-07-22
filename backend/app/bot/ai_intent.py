"""Free-text log parsing via the LLM — the «залив 40л на окко за 2200» path.

When the deterministic parsers miss, the model classifies the message into one
of the actions the bot already supports (refuel / expense / odometer) and pulls
the numbers out. Best-effort: None on no key, quota, timeout or an unrecognised
message, so the bot just answers «не зрозумів» exactly as before.
"""

from __future__ import annotations

from typing import Optional

from app.services.ocr_llm import ask_gemini_json_text

_ACTIONS = ("refuel", "expense", "odometer")

_PROMPT = """Ти — парсер повідомлень авто-логбука. Користувач пише коротке повідомлення українською АБО англійською про свою машину. Визнач ОДНУ дію і витягни числа. `title` став тією ж мовою, що й повідомлення. Поверни ЛИШЕ JSON:
{
  "action": "refuel" | "expense" | "odometer" | "none",
  "liters": число або null,
  "price_per_liter": число або null,
  "total_cost": число або null,
  "gas_station": рядок або null,
  "is_full_tank": true/false/null,
  "odometer": ціле або null,
  "title": рядок або null
}
Правила:
- Є літри/паливо/АЗС (litres/fuel/fill-up/gas station) -> action="refuel" (gas_station: ОККО/WOG/SOCAR/UPG/Amic/Shell тощо).
- Будь-яка інша витрата (мийка/car wash, штраф/fine, страховка/insurance, ремонт/repair, ТО/service, робота СТО) -> action="expense", title = коротка назва.
- Лише показник пробігу («пробіг 154000», «154 тис км», «mileage 154000», «154k km») -> action="odometer".
- Незрозуміло -> action="none".
- Числа без валют/одиниць. «2.2к»/«2,2к» = 2200. Кома — десятковий роздільник.
ПОВІДОМЛЕННЯ: """


def _num(value: object) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value > 0 else None


def refuel_fields_from_intent(intent: dict) -> Optional[dict]:
    """Fill in the missing one of litres / price / total from the other two.

    Returns the four refuel fields (litres, price_per_liter, total_cost,
    gas_station) or None when fewer than two of the numbers are present.
    """
    liters = _num(intent.get("liters"))
    price = _num(intent.get("price_per_liter"))
    total = _num(intent.get("total_cost"))

    if liters and price and total is None:
        total = round(liters * price, 2)
    elif liters and total and price is None:
        price = round(total / liters, 2)
    elif price and total and liters is None:
        liters = round(total / price, 2)

    if not (liters and price and total):
        return None
    station = intent.get("gas_station")
    return {
        "liters": liters,
        "price_per_liter": price,
        "total_cost": total,
        "gas_station": station.strip() if isinstance(station, str) and station.strip() else None,
    }


def parse_message_intent(text: str) -> Optional[dict]:
    """Classify a free-text message, or None if the model can't (or isn't there)."""
    data = ask_gemini_json_text(_PROMPT + text.strip()[:300])
    if not isinstance(data, dict) or data.get("action") not in _ACTIONS:
        return None
    return data
