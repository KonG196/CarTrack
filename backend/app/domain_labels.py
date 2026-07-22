"""Display labels for canonical, persisted domain values (backend mirror of the
frontend `src/i18n/domain.js`).

The values themselves — maintenance item names, repair/expense categories — are
stored in Ukrainian and matched by other code, so they never change. Only what a
user *sees* (in the PDF report, the bot) is localized here: Ukrainian is the
identity (the value is already its own Ukrainian label), English is looked up
with a passthrough fallback so free-text custom values survive untouched.

Fuel *type* is a code (petrol/diesel/…), so it has an explicit map per language.
"""

from __future__ import annotations

from app.i18n import normalize_lang

_EN = {
    "maintenance": {
        "Олива двигуна": "Engine oil",
        "Масляний фільтр": "Oil filter",
        "Повітряний фільтр": "Air filter",
        "Салонний фільтр": "Cabin filter",
        "Паливний фільтр": "Fuel filter",
        "Гальмівна рідина": "Brake fluid",
    },
    "repair": {
        "Підвіска": "Suspension",
        "Гальма": "Brakes",
        "Двигун": "Engine",
        "Електрика": "Electrical",
        "Трансмісія": "Transmission",
        "Кузов": "Body",
        "Інше": "Other",
    },
    "expense": {
        "Мийка": "Car wash",
        "Паркування": "Parking",
        "Штраф": "Fine",
        "Страхування": "Insurance",
        "Податок": "Tax",
        "Шини": "Tires",
        "Аксесуари": "Accessories",
        "Інше": "Other",
    },
}

_FUEL = {
    "en": {"petrol": "Petrol", "diesel": "Diesel", "lpg": "LPG", "electric": "Electric", "hybrid": "Hybrid"},
    "uk": {"petrol": "Бензин", "diesel": "Дизель", "lpg": "ГБО", "electric": "Електро", "hybrid": "Гібрид"},
}


def _label(group: str, value: str | None, lang: str) -> str | None:
    if value is None or value == "":
        return value
    if normalize_lang(lang) != "en":
        return value  # Ukrainian value is already the Ukrainian label
    return _EN[group].get(value, value)  # unknown / custom → passthrough


def maintenance_item_label(value: str | None, lang: str = "en") -> str | None:
    return _label("maintenance", value, lang)


def repair_category_label(value: str | None, lang: str = "en") -> str | None:
    return _label("repair", value, lang)


def expense_category_label(value: str | None, lang: str = "en") -> str | None:
    return _label("expense", value, lang)


def fuel_type_label(code: str | None, lang: str = "en") -> str:
    if not code:
        return code or ""
    return _FUEL[normalize_lang(lang)].get(code, code)
