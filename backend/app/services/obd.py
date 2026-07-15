"""Car Scanner (ELM OBD2) CSV import: parsing, downsampling, health verdicts.

Pure functions only — no database, no I/O. The router owns storage.

Car Scanner exports one column per PID, but the header text is not a contract:
it changes between app versions, profiles and interface languages (Ukrainian,
English, Russian), and it usually carries the unit in parentheses. So columns
are matched to canonical metric keys by fuzzy comparison rather than by exact
name, and anything unrecognized is handed back in ``unmapped_columns`` instead
of being silently dropped.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
from typing import Iterable, Optional, Sequence

# Points kept per metric series. A 40-minute log at 1 Hz is ~2400 samples per
# PID; the charts are ~360 px wide, so storing more would cost rows nobody can
# see. The raw CSV is not kept at all (documented limitation).
MAX_SERIES_POINTS = 200

Sample = tuple[float, float]


class ObdParseError(ValueError):
    """The text is not a Car Scanner CSV we can read."""


# Column mapping

# Patterns are matched as substrings against the normalized header. Ukrainian
# entries are stems on purpose: the same PID appears as «Маса сажі» and «Сажа»,
# and declension would defeat whole-word patterns.
METRIC_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Specific DPF columns first: «distance since dpf regeneration» also
    # contains «dpf», which the soot patterns must not claim.
    (
        "dpf_distance_since_regen",
        ("distancesince", "пробігзостанньої", "регенерац", "regeneration"),
    ),
    ("dpf_soot_mass", ("sootmass", "dpfsoot", "soot", "масасажі", "саж")),
    ("battery_voltage", ("controlmodulevoltage", "batteryvoltage", "voltage", "напруг")),
    ("coolant_temp", ("coolanttemp", "температураож", "температураоp", "охолодж")),
    ("intake_temp", ("intakeairtemp", "intaketemp", "температуравпуск", "впускногоповітря")),
    ("fuel_rail_pressure", ("fuelrailpressure", "railpressure", "тискупаливнійрампі", "паливнійрампі")),
    ("boost_pressure", ("boost", "тискнаддуву", "наддув")),
    ("engine_rpm", ("enginerpm", "rpm", "enginespeed", "обертидвигуна", "оберти")),
    ("vehicle_speed", ("vehiclespeed", "speed", "швидкість")),
)

# Ranges outside which a reading is bus noise rather than a measurement: a
# 999 g soot mass or a -300 °C coolant is the ELM adapter talking, not the car.
SANITY_RANGES: dict[str, tuple[float, float]] = {
    "dpf_soot_mass": (0.0, 100.0),
    "battery_voltage": (6.0, 18.0),
    "coolant_temp": (-40.0, 150.0),
    "intake_temp": (-40.0, 150.0),
    "injector_correction_1": (-10.0, 10.0),
    "injector_correction_2": (-10.0, 10.0),
    "injector_correction_3": (-10.0, 10.0),
    "injector_correction_4": (-10.0, 10.0),
}

INJECTOR_PATTERNS: tuple[str, ...] = (
    "injectorcorrection",
    "injectorcorr",
    "корекціяфорсунк",
    "форсунк",
)

TIME_PATTERNS: tuple[str, ...] = ("time", "seconds", "час", "timestamp", "секунд")

# Cells Car Scanner writes when a PID did not answer on that tick.
BLANK_CELLS: frozenset[str] = frozenset({"", "-", "--", "—", "nan", "n/a", "na", "null", "?"})

_UNIT_RE = re.compile(r"\(([^)]*)\)")
_PAREN_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_KEEP_RE = re.compile(r"[^0-9a-zа-яёіїєґ]+")


def normalize_header(name: str) -> str:
    lowered = (name or "").lower().replace("ё", "е").replace("’", "").replace("'", "")
    without_units = _PAREN_RE.sub(" ", lowered)
    return _KEEP_RE.sub("", without_units)


def header_unit(name: str) -> str:
    match = _UNIT_RE.search(name or "")
    if not match:
        return ""
    return match.group(1).strip()[:20]


def _injector_key(normalized: str) -> Optional[str]:
    is_injector = any(pattern in normalized for pattern in INJECTOR_PATTERNS) or (
        "cylinder" in normalized and "correction" in normalized
    )
    if not is_injector:
        return None
    cylinder = re.search(r"[1-4]", normalized)
    return f"injector_correction_{cylinder.group()}" if cylinder else None


def map_column(name: str) -> Optional[str]:
    normalized = normalize_header(name)
    if not normalized:
        return None
    injector = _injector_key(normalized)
    if injector:
        return injector
    for key, patterns in METRIC_PATTERNS:
        if any(pattern in normalized for pattern in patterns):
            return key
    return None


def is_time_column(name: str) -> bool:
    normalized = normalize_header(name)
    return any(pattern in normalized for pattern in TIME_PATTERNS)


# Cell parsing


def parse_number(raw: str) -> Optional[float]:
    text = (raw or "").strip().replace("\xa0", "").replace(" ", "")
    if text.lower() in BLANK_CELLS:
        return None
    if "," in text and "." in text:
        # "1,234.5" — the comma groups thousands.
        text = text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        value = float(text)
    except ValueError:
        return None
    # NaN/inf poison JSON and every aggregate downstream.
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return value


_TIME_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%d.%m.%Y %H:%M:%S.%f",
    "%d.%m.%Y %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%H:%M:%S.%f",
    "%H:%M:%S",
)


def parse_timestamp(raw: str) -> Optional[dt.datetime]:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in _TIME_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _detect_delimiter(lines: Sequence[str]) -> str:
    for line in lines:
        semicolons, commas = line.count(";"), line.count(",")
        if semicolons or commas:
            return ";" if semicolons > commas else ","
    return ","


def _content_lines(text: str) -> list[str]:
    lines = text.splitlines()
    start = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        start = index
        break
    else:
        return []
    return [line for line in lines[start:] if line.strip()]


# Parsing


def parse_obd_csv(text: str) -> dict:
    lines = _content_lines(text or "")
    if not lines:
        raise ObdParseError("Файл порожній")

    delimiter = _detect_delimiter(lines)
    rows = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter))
    if not rows:
        raise ObdParseError("Не вдалося прочитати CSV")

    header = [cell.strip().lstrip("﻿") for cell in rows[0]]
    if len(header) < 2 or not is_time_column(header[0]):
        raise ObdParseError(
            "Не знайдено колонку часу — це не схоже на лог Car Scanner"
        )

    # Column index -> canonical key. First column wins a key: a duplicate PID
    # (same metric logged twice) would otherwise overwrite the earlier series.
    mapped: dict[int, str] = {}
    unmapped: list[str] = []
    for index, name in enumerate(header[1:], start=1):
        key = map_column(name)
        if key is None or key in mapped.values():
            if name:
                unmapped.append(name)
            continue
        mapped[index] = key

    times: list[float] = []
    recorded_at: Optional[dt.datetime] = None
    origin: Optional[dt.datetime] = None
    samples: dict[int, list[Sample]] = {index: [] for index in mapped}

    for row in rows[1:]:
        if not row or len(row) < 2:
            continue
        seconds = parse_number(row[0])
        if seconds is None:
            stamp = parse_timestamp(row[0])
            if stamp is None:
                continue  # a stray comment or a repeated header
            if origin is None:
                origin, recorded_at = stamp, stamp
            seconds = (stamp - origin).total_seconds()
        times.append(seconds)

        for index, key in mapped.items():
            if index >= len(row):
                continue
            value = parse_number(row[index])
            if value is None:
                continue
            low, high = SANITY_RANGES.get(key, (float("-inf"), float("inf")))
            if not low <= value <= high:
                continue
            samples[index].append((seconds, value))

    if not times:
        raise ObdParseError("У файлі немає рядків даних")

    metrics = [
        {
            "key": key,
            "source_column": header[index],
            "unit": header_unit(header[index]),
            "samples": samples[index],
        }
        for index, key in mapped.items()
        if samples[index]
    ]
    for index, key in mapped.items():
        # A column that mapped but whose every reading was junk is not a
        # metric — report it so the UI can say the PID came back empty.
        if not samples[index]:
            unmapped.append(header[index])

    return {
        "recorded_at": recorded_at,
        "duration_s": round(max(times) - min(times), 3),
        "metrics": metrics,
        "unmapped_columns": unmapped,
        "sample_count": len(times),
    }


# Downsampling and summaries


def downsample(samples: Sequence[Sample], limit: int = MAX_SERIES_POINTS) -> list[Sample]:
    """Thin a series to at most ``limit`` points, keeping shape and extremes.

    Evenly spaced picks preserve the curve; the min and the max are forced back
    in because they are the whole point of a diagnostic chart — a downsample
    that loses the soot peak loses the diagnosis.
    """
    count = len(samples)
    if count <= limit:
        return list(samples)

    values = [value for _, value in samples]
    extremes = {
        min(range(count), key=values.__getitem__),
        max(range(count), key=values.__getitem__),
    }
    # The extremes are reserved out of the budget first, so the result honours
    # the limit even when both fall between the evenly spaced picks.
    spread = max(limit - len(extremes), 1)
    picks = (
        {round(i * (count - 1) / (spread - 1)) for i in range(spread)}
        if spread > 1
        else {0}
    )
    return [samples[index] for index in sorted(picks | extremes)]


def summarize(key: str, unit: str, samples: Sequence[Sample]) -> dict:
    """Aggregate a full series into the stored row (stats + capped series).

    min/max/avg/last are computed over every sample, not over the downsample:
    the stats must describe the drive, not the picture of it.
    """
    values = [value for _, value in samples]
    return {
        "key": key,
        "unit": unit,
        "min": min(values),
        "max": max(values),
        "avg": round(sum(values) / len(values), 4),
        "last": values[-1],
        "series": downsample(samples),
    }


# Health verdicts — Ukrainian, owner-facing

DPF_SOOT_CRIT = 24.0
DPF_SOOT_WARN = 18.0
INJECTOR_SPREAD_WARN = 3.0
INJECTOR_ABS_CRIT = 5.0
BATTERY_CRANK_CRIT = 9.6
BATTERY_REST_WARN = 12.2


def _verdict(key: str, level: str, text: str) -> dict:
    return {"key": key, "level": level, "text": text}


def dpf_verdict(
    soot_last: Optional[float], distance_since_regen: Optional[float] = None
) -> Optional[dict]:
    if soot_last is None:
        return None
    tail = (
        f" З останньої регенерації — {distance_since_regen:.0f} км."
        if distance_since_regen is not None
        else ""
    )
    reading = f" Сажа: {soot_last:.1f} г."
    if soot_last > DPF_SOOT_CRIT:
        return _verdict(
            "dpf", "crit", f"🔴 Критично: сажовий фільтр потребує уваги.{reading}{tail}"
        )
    if soot_last > DPF_SOOT_WARN:
        return _verdict("dpf", "warn", f"🟡 Регенерація скоро.{reading}{tail}")
    return _verdict("dpf", "ok", f"🟢 В нормі.{reading}{tail}")


def injector_verdict(corrections: Sequence[Optional[float]]) -> Optional[dict]:
    # Cylinder numbers come from the position, so a car that only logged
    # cylinders 3 and 4 still gets its fault named correctly.
    known = [
        (cylinder, value)
        for cylinder, value in enumerate(corrections, start=1)
        if value is not None
    ]
    if not known:
        return None

    cylinder, worst = max(known, key=lambda pair: abs(pair[1]))
    if abs(worst) > INJECTOR_ABS_CRIT:
        return _verdict(
            "injectors",
            "crit",
            f"🔴 Перевірити форсунку {cylinder} — корекція {worst:+.1f} mm³.",
        )
    values = [value for _, value in known]
    spread = max(values) - min(values)
    if spread > INJECTOR_SPREAD_WARN:
        return _verdict(
            "injectors", "warn", f"🟡 Форсунки розбалансовані — розкид {spread:.1f} mm³."
        )
    return _verdict("injectors", "ok", f"🟢 Форсунки збалансовані — розкид {spread:.1f} mm³.")


def battery_verdict(voltage_min: Optional[float]) -> Optional[dict]:
    if voltage_min is None:
        return None
    if voltage_min < BATTERY_CRANK_CRIT:
        return _verdict(
            "battery", "crit", f"🔴 АКБ просідає — {voltage_min:.1f} В при старті."
        )
    if voltage_min < BATTERY_REST_WARN:
        return _verdict("battery", "warn", f"🟡 Недозаряд — мінімум {voltage_min:.1f} В.")
    return _verdict("battery", "ok", f"🟢 Живлення в нормі — мінімум {voltage_min:.1f} В.")


def session_verdicts(summaries: Iterable[dict]) -> list[dict]:
    by_key = {summary["key"]: summary for summary in summaries}

    def last_of(key: str) -> Optional[float]:
        summary = by_key.get(key)
        return summary["last"] if summary else None

    corrections = [
        by_key[f"injector_correction_{cylinder}"]["last"]
        if f"injector_correction_{cylinder}" in by_key
        else None
        for cylinder in (1, 2, 3, 4)
    ]
    battery = by_key.get("battery_voltage")
    verdicts = [
        dpf_verdict(last_of("dpf_soot_mass"), last_of("dpf_distance_since_regen")),
        injector_verdict(corrections),
        battery_verdict(battery["min"] if battery else None),
    ]
    return [verdict for verdict in verdicts if verdict is not None]
