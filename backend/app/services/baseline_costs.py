"""Ballpark costs for a service this car has never had logged.

History always wins. This is what to show instead of nothing on the first
service of a car nobody has driven here yet — a number to argue with rather
than an empty field, and it must always be labelled as such: a market ballpark
that looks like the user's own data is worse than no number, because they would
have no reason to check it.

**It is priced for the car in front of it, not for an average car.** The signals
are the ones the app already holds and can defend:

- **The user's own specs.** «Олива двигуна: ~4.6 л» in the car's spec sheet is a
  fact they recorded off the service passport. Nothing here beats it.
- **Engine displacement**, parsed from the `engine` field: oil volume scales with
  it, and volume is most of the bill for an oil change.
- **Fuel type.** Not for the oil price — that turned out to be a false signal,
  see below — but for whether a service exists at all. An electric car has no
  engine oil, no fuel filter, no timing belt and no spark plugs; a diesel has no
  spark plugs; a diesel fuel filter is a real service item where a petrol one is
  often in-tank for life.

Returning None for «this car does not have that» is the point of the fuel-type
rules. Quoting a Tesla owner 3500 ₴ for an oil change is not a ballpark, it is
nonsense with a currency sign.

**What was deliberately NOT encoded.** The obvious guess — diesel oil costs more
— does not survive checking. VW 507.00 low-SAPS oils are approved for petrol and
diesel alike, and the per-litre prices overlap: Mobil Super 3000 ~381 ₴/л,
Castrol Magnatec ~552 ₴/л, Total Quartz INEO (504/507) ~442 ₴/л, Shell Helix
Ultra (504/507) ~686 ₴/л. A fuel-type multiplier on oil price would be invented
precision, so there is one price per litre and the volume does the work.

Researched 2026-07-16 from Ukrainian shops and price lists:
- Робота: заміна оливи 300-500, повітряний фільтр 200, салонний 300-700,
  паливний від 500, гальмівна рідина 600-800, антифриз 850, діагностика 200-500
  (avtoservis.lviv.ua/price, genstar.ua, autocar-service.lviv.ua)
- Олива 5W-30: 381-700 ₴/л залежно від допуску (exist.ua, maslobaza.com,
  avtozvuk.ua)
- ГРМ: робота 1900-2500 звичайно, комплект від 600 (no-name) до кількох тисяч
  (profigas.ua/zamina-grm)

Deliberately absent: ОСЦПВ, техогляд, зелена карта, транспортний податок. The
policy alone runs 2100-10000 ₴ depending on region, engine and the driver's
bonus-malus — a fivefold spread is not a ballpark, it is noise wearing one.
Транспортний податок is 0 ₴ for anything but a near-new luxury car, so a
non-zero guess there would be simply wrong.

These prices still go stale, and they still know nothing about the city or the
shop. That is what history is for, and history is always preferred.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Callable, Optional

RESEARCHED_ON = dt.date(2026, 7, 16)

# One price for a litre of 5W-30, because the spread by approval overlaps the
# spread by brand — see the module docstring.
_OIL_PER_LITRE = 500
_OIL_FILTER = 600
_OIL_LABOUR = 400

# Sump capacity against displacement, least-squares over six real engines:
# 1.0 TSI 4.0 л, Lanos 1.5 3.75, Golf 1.6 TDI 4.6, 2.0 TDI 4.3, 2.0 TSI 5.7,
# 3.0 TDI V6 7.9.
#
# The fit is loose on purpose, and the scatter is worth knowing before trusting
# it: it lands within ~1 л, and no line can do better, because two different
# 2.0 engines take 4.3 and 5.7. Displacement is a hint, not a lookup — which is
# exactly why a volume off the owner's own spec sheet outranks it.
_OIL_LITRES_BASE = 1.2
_OIL_LITRES_PER_L = 2.1
_OIL_LITRES_RANGE = (3.0, 9.0)
_OIL_LITRES_DEFAULT = 4.5

_COMBUSTION = ("petrol", "diesel", "lpg", "hybrid")
_SPARKS = ("petrol", "lpg", "hybrid")


@dataclass(frozen=True)
class CarProfile:
    """What the estimator is allowed to know about the car.

    Every field is optional: a car added in ten seconds has a fuel type and
    little else, and the ballpark still has to work.
    """

    fuel_type: Optional[str] = None
    displacement_l: Optional[float] = None
    # From the car's own spec sheet, if the owner filled it in.
    oil_litres: Optional[float] = None


_EMPTY = CarProfile()


def oil_litres_for(profile: CarProfile) -> float:
    """How much oil this engine takes: recorded, else derived, else typical."""
    if profile.oil_litres:
        return profile.oil_litres
    if profile.displacement_l:
        litres = _OIL_LITRES_BASE + _OIL_LITRES_PER_L * profile.displacement_l
        return round(min(max(litres, _OIL_LITRES_RANGE[0]), _OIL_LITRES_RANGE[1]), 1)
    return _OIL_LITRES_DEFAULT


def _burns_fuel(profile: CarProfile) -> bool:
    """Unknown counts as yes: most cars burn something, and refusing to price a
    service because the fuel type is blank helps nobody."""
    return profile.fuel_type is None or profile.fuel_type in _COMBUSTION


def _oil_change(profile: CarProfile) -> Optional[int]:
    if not _burns_fuel(profile):
        return None
    oil = oil_litres_for(profile) * _OIL_PER_LITRE
    return int(round(oil + _OIL_FILTER + _OIL_LABOUR, -1))


def _fuel_filter(profile: CarProfile) -> Optional[int]:
    if not _burns_fuel(profile):
        return None
    # A diesel filter is a service item and a dear one. On petrol it is often
    # in the tank and left alone for the life of the car, so the ballpark is
    # what the cheaper job costs when it is done at all.
    return 1900 if profile.fuel_type == "diesel" else 1200


def _spark_plugs(profile: CarProfile) -> Optional[int]:
    if profile.fuel_type is not None and profile.fuel_type not in _SPARKS:
        return None
    return 1600


def _timing_belt(profile: CarProfile) -> Optional[int]:
    if not _burns_fuel(profile):
        return None
    return 8000


def _flat(amount: int) -> Callable[[CarProfile], Optional[int]]:
    return lambda profile: amount


@dataclass(frozen=True)
class Baseline:
    # Every stem must appear. One is never enough: «Фільтр масляний» says «масл»
    # and is not oil — matching on one word would price a 600 ₴ filter as a
    # whole oil service.
    needs: tuple[str, ...]
    # The stems that rule this line out.
    never: tuple[str, ...]
    # None means this car does not have that service at all.
    price: Callable[[CarProfile], Optional[int]]
    # What the number is made of, so it can be argued with instead of trusted.
    made_of: str


# Filters before oil: «Фільтр масляний» must be claimed by the filter rule.
_BASELINES: tuple[Baseline, ...] = (
    Baseline(("фільтр", "масл"), (), _flat(700), "фільтр ~600 + робота разом із оливою"),
    Baseline(("фільтр", "повітр"), (), _flat(800), "фільтр ~600 + робота ~200"),
    Baseline(("фільтр", "салон"), (), _flat(900), "фільтр ~600 + робота ~300"),
    Baseline(("фільтр", "палив"), (), _fuel_filter, "дизельний ~1400 + робота ~500; бензиновий дешевший"),
    Baseline(("рідин", "гальм"), (), _flat(1150), "рідина ~450 + прокачка ~700"),
    Baseline(("гальмівна рідина",), (), _flat(1150), "рідина ~450 + прокачка ~700"),
    Baseline(("грм",), (), _timing_belt, "комплект ~5000 + робота ~3000; з помпою помітно більше"),
    Baseline(("антифриз",), (), _flat(1650), "рідина ~800 + робота ~850"),
    Baseline(("охолодж",), (), _flat(1650), "рідина ~800 + робота ~850"),
    Baseline(("олив",), ("фільтр",), _oil_change, "обʼєм двигуна × ~500 ₴/л + фільтр ~600 + робота ~400"),
    Baseline(("мастил",), ("фільтр",), _oil_change, "обʼєм двигуна × ~500 ₴/л + фільтр ~600 + робота ~400"),
    Baseline(("масло",), ("фільтр",), _oil_change, "обʼєм двигуна × ~500 ₴/л + фільтр ~600 + робота ~400"),
    Baseline(("діагностик",), (), _flat(400), "робота 200-500"),
    Baseline(("колодк",), (), _flat(2500), "колодки ~1800 + робота ~700"),
    Baseline(("свічк",), (), _spark_plugs, "свічки ~1200 + робота ~400; дизель їх не має"),
)

_DISPLACEMENT_LITRES_RE = re.compile(r"\b([0-9])[.,]([0-9])\b")
_DISPLACEMENT_CC_RE = re.compile(r"\b(\d{3,4})\s*(?:см3|cm3|cc|куб)")
_SPEC_LITRES_RE = re.compile(r"([\d]+(?:[.,]\d+)?)\s*л\b")


def parse_displacement(engine: Optional[str]) -> Optional[float]:
    """«1.6 TDI» -> 1.6, «1598 см3» -> 1.6. The field is free text, so it is
    read rather than trusted: anything outside a plausible engine is dropped."""
    if not engine:
        return None
    text = engine.lower()
    match = _DISPLACEMENT_CC_RE.search(text)
    if match:
        litres = int(match.group(1)) / 1000
        return round(litres, 1) if 0.5 <= litres <= 8.0 else None
    match = _DISPLACEMENT_LITRES_RE.search(text)
    if match:
        litres = float(f"{match.group(1)}.{match.group(2)}")
        return litres if 0.5 <= litres <= 8.0 else None
    return None


def parse_spec_litres(value: Optional[str]) -> Optional[float]:
    """«~4.6 л» -> 4.6."""
    if not value:
        return None
    match = _SPEC_LITRES_RE.search(value.replace(",", "."))
    if not match:
        return None
    litres = float(match.group(1))
    return litres if _OIL_LITRES_RANGE[0] <= litres <= _OIL_LITRES_RANGE[1] else None


def _matches(lowered: str, baseline: Baseline) -> bool:
    if any(stem in lowered for stem in baseline.never):
        return False
    return all(stem in lowered for stem in baseline.needs)


def baseline_for(title: str) -> Optional[Baseline]:
    lowered = re.sub(r"\s+", " ", (title or "").lower()).strip()
    if not lowered:
        return None
    for baseline in _BASELINES:
        if _matches(lowered, baseline):
            return baseline
    return None


def baseline_cost(title: str, profile: Optional[CarProfile] = None) -> Optional[float]:
    """The ballpark for this service on this car, or None when there is none.

    None is a real answer, not a gap to fill. It means either that nothing here
    knows the service — a policy, a tax, a title the user invented — or that this
    car does not have it, which is the only honest thing to say about an oil
    change on an electric car.
    """
    baseline = baseline_for(title)
    if baseline is None:
        return None
    amount = baseline.price(profile or _EMPTY)
    return float(amount) if amount is not None else None
