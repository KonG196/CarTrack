"""Clean car photos from Wikimedia Commons — free, no watermark, no attribution.

The dedicated render services (carimagesapi, imagin) watermark their free tier
across the whole car. Wikimedia Commons, filtered to CC0 / public-domain files
(`haslicense:unrestricted`), gives real, licence-clean photos of the actual
make/model with NO watermark and NO attribution requirement. We only ever use
CC0/PD results; a car with none simply gets no photo (like the old placeholder
case), so there is never a licence obligation to display a credit.

We store only the resolved image URL (a stable upload.wikimedia.org link), never
the file — the browser caches the file, and Wikimedia asks us not to leech, so we
resolve once per car and cache the URL. get_car_image(db, car) returns a URL or
None:
  - a fresh cached URL           → returned, zero API calls
  - a car marked image_missing   → None (with a soft recheck window)
  - otherwise                    → one Commons search, cached, returned

Best-effort throughout: any failure yields None or the last good URL, never an
exception, so the dashboard just shows no photo.
"""

from __future__ import annotations

import datetime as dt
import logging
import re

import httpx
from sqlalchemy.orm import Session

from app.car_logos import LOGO_SLUGS
from app.models import Car

logger = logging.getLogger(__name__)

# Marque logos (filippofilip95/car-logos-dataset, MIT) via the jsDelivr CDN — a
# clean fallback when no car photo exists. Shown to identify the user's own car,
# so nominative use of the trademark; nothing is re-hosted.
_LOGO_CDN = (
    "https://cdn.jsdelivr.net/gh/filippofilip95/car-logos-dataset@master"
    "/logos/thumb/{slug}.png"
)

# Post-Soviet marques written in Cyrillic → their Latin dataset slug.
_BRAND_ALIASES = {
    "газ": "gaz",
    "заз": "zaz",
    "ваз": "lada",
    "лада": "lada",
    "уаз": "uaz",
    "зіл": "zil",
    "зил": "zil",
    "камаз": "kamaz",
    "москвич": "moskvich",
    "таврія": "zaz",
}

_COMMONS_API = "https://commons.wikimedia.org/w/api.php"
# Wikimedia requires a descriptive User-Agent with contact info, or requests are
# throttled hard (10/min vs 200/min). See phabricator T224891.
_USER_AGENT = (
    "KapotTracker/1.0 (https://kapot-tracker.vercel.app; maks060691@gmail.com)"
)
_TIMEOUT = 8.0
_THUMB_WIDTH = 600
# upload.wikimedia.org URLs are stable, so we cache long and only re-resolve to
# pick up a possibly-better photo occasionally.
_CACHE_DAYS = 30
# Don't re-probe a car we just found imageless too often.
_MISSING_RECHECK_DAYS = 14


def car_image_enabled() -> bool:
    # Wikimedia needs no key; the feature is always available. The flag exists so
    # tests and callers can reason about it uniformly.
    return True


def _utcnow() -> dt.datetime:
    return dt.datetime.utcnow()


def _fresh(car: Car) -> bool:
    return bool(
        car.image_url
        and car.image_expires_at
        and car.image_expires_at > _utcnow()
    )


def get_car_image(db: Session, car: Car) -> str | None:
    """Return a usable CC0 image URL for the car, or None. Applies the cache."""
    if car.image_missing and car.image_checked_at:
        if _utcnow() - car.image_checked_at < dt.timedelta(days=_MISSING_RECHECK_DAYS):
            return None
    if _fresh(car):
        return car.image_url

    url = _resolve(car)
    car.image_checked_at = _utcnow()
    if url is None:
        car.image_missing = True
        car.image_url = None
        car.image_expires_at = None
        db.commit()
        return None
    car.image_url = url
    car.image_expires_at = _utcnow() + dt.timedelta(days=_CACHE_DAYS)
    car.image_missing = False
    db.commit()
    return url


# Prefer neutral body colours — random CC0 shots are often odd colours or bad
# framing. Commons is text-searched, but photographers put the colour in the file
# name/description, so adding one colour word biases toward it. Tried ONE at a
# time (combining them ORs the query and returns junk).
_NEUTRAL_COLOURS = ("white", "silver", "grey", "black")
# A landscape shot at least this wide is a proper car photo, not a cropped or
# distant one — the filter that kills the "tiny car in the corner" results.
_MIN_WIDTH = 800
# File-name words that flag a photo we don't want as "the car": motorsport,
# wrecks, cutaways, interiors. A hit skips that result.
_NAME_BLOCKLIST = (
    "rally", "race", "racing", "wrc", "motorsport", "tuning", "modified",
    "crash", "accident", "wreck", "burnt", "fire", "cutaway", "engine",
    "interior", "dashboard", "chassis", "police", "taxi",
    # High-performance / luxury variants that aren't the plain model.
    "amg", "maybach", "brabus", "-rs ", " rs ", "abarth",
    # Multi-vehicle shots where this car isn't the subject.
    "unimog", " and ", " trio", "lineup", "line-up",
    # Framing we don't want as the headline shot.
    "rearview", "rear view", "rear_view", "rear-view", "the rear", "backview",
    "underside", "undercarriage", "badge", "logo", "wheel", "detail",
)
# A file name mentioning the front reads as a clean headline shot — nudge it up.
_FRONT_HINTS = ("front", "frontview", "front view", "front-view")


_ROMANS = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


def _generation_terms(car: Car) -> list[str]:
    """Ways to name the car's generation so Commons pins the RIGHT one — a Golf
    «7 (BA5)» must not match a Mk6, a Passat «B7» must not match a B5. Built from
    the leading token of the `generation` field, in the forms Commons uses.

    - a plain number «7 (BA5)»  → ["Mk7", "VII"]
    - a coded gen «B7», «W205» → ["B7"] (used verbatim — that's how Commons names
      Passat/Mercedes generations)
    Empty when there's no generation to go on."""
    gen = (car.generation or "").strip()
    if not gen:
        return []
    token = gen.split()[0].split(",")[0].strip()  # "7 (BA5)" → "7"; "B7" → "B7"
    if not token:
        return []
    # A bare number → the Mk / Roman forms.
    if token.isdigit():
        n = int(token)
        if 1 <= n <= 12:
            return [f"Mk{n}", _ROMANS[n]]
        return []
    # A coded generation (B7, W205, E90…) — Commons uses it as-is.
    if re.match(r"^[A-Za-z]+\d", token):
        return [token.upper()]
    return []


_TRIM_WORDS = frozenset(
    {"tsi", "tdi", "tfsi", "cdi", "hybrid", "4matic", "quattro", "amg", "hdi", "dci"}
)


def _clean_model(model: str) -> str:
    """Drop a trailing trim/engine level from the model so the search matches a
    catalogue photo — Commons files are named by model, not by trim. E.g.
    "Gls 350" → "GLS", "Passat 2.0" → "Passat", "3 Series 320d" → "3 Series".

    The FIRST token is always kept (it may be the model itself, like "3" in "3
    Series"). After that, a token that looks like an engine/trim level — an
    engine word, a displacement (2.0), or a spec code (320d, 350, 63) — ends the
    model and everything from it on is dropped."""
    parts = model.strip().split()
    if not parts:
        return model.strip()
    kept = [parts[0]]
    for part in parts[1:]:
        low = part.lower()
        is_trim = (
            low in _TRIM_WORDS
            or re.fullmatch(r"\d+\.\d+", part)  # displacement 2.0, 1.6
            or re.fullmatch(r"\d{2,4}[a-z]{0,3}", low)  # 350, 320d, 63, 400d
        )
        if is_trim:
            break
        kept.append(part)
    return " ".join(kept)


def _resolve(car: Car) -> str | None:
    """Find a decent CC0 Commons photo of the RIGHT generation of the car,
    preferring a proper landscape framing and a neutral colour.

    Getting the GENERATION right matters most — a "Golf 7" must not show a Mk6, a
    "Passat B7" must not show a B5 — so the generation tag leads and is tried on
    its OWN first: adding a colour word can pull a wrong-generation photo whose
    file name happens to carry that colour. Colour is a secondary nicety. The raw
    YEAR is avoided (it drags in motorsport shots whose names carry the year).
    The model is stripped of its trim/engine level, which Commons doesn't name
    files by and which otherwise narrows the search to nothing."""
    base = f"{car.brand} {_clean_model(car.model)}".strip()
    gens = _generation_terms(car)  # e.g. ["Mk7", "VII"] or ["B7"], or []

    # Pass 1: generation alone — the surest way to the right car. Year-filtered
    # too, so a model+trim that also matches an OLDER generation's photo (e.g.
    # "3 Series 320d" hitting an E90) can't slip a wrong-era shot through.
    for gen in gens:
        url = _search(
            f"{base} {gen}",
            require_landscape=True,
            car_year=car.year,
            year_tolerance=_YEAR_TOLERANCE_WITH_GEN,
        )
        if url:
            return url
    # Pass 2: generation + neutral colour — right car, nicer colour.
    for gen in gens:
        for colour in _NEUTRAL_COLOURS:
            url = _search(
                f"{base} {gen} {colour}",
                require_landscape=True,
                car_year=car.year,
                year_tolerance=_YEAR_TOLERANCE_WITH_GEN,
            )
            if url:
                return url
    # No explicit generation → the YEAR is the best clue to the right era, so a
    # 2013 Sportage doesn't come back as the newest one. The blocklist keeps the
    # motorsport/year-in-name junk out that made us drop the year for known
    # generations.
    if not gens and car.year:
        # Pass 3: year alone — pins the generation for the era. The year filter
        # also rejects a photo from a clearly different model year.
        url = _search(f"{base} {car.year}", require_landscape=True, car_year=car.year)
        if url:
            return url
        # Pass 4: year + neutral colour.
        for colour in _NEUTRAL_COLOURS:
            url = _search(
                f"{base} {car.year} {colour}", require_landscape=True, car_year=car.year
            )
            if url:
                return url
    # Pass 5: model + neutral colour, still rejecting far-off years.
    for colour in _NEUTRAL_COLOURS:
        url = _search(f"{base} {colour}", require_landscape=True, car_year=car.year)
        if url:
            return url
    # Pass 6: any wide landscape shot of the model (year-filtered).
    url = _search(base, require_landscape=True, car_year=car.year)
    if url:
        return url
    # Pass 7: last resort — accept anything.
    for terms in ([f"{base} {car.year}", base] if car.year else [base]):
        url = _search(terms, require_landscape=False)
        if url:
            return url
    return None


# A photo whose file name carries a model year this far from the car's year is a
# different generation — skip it (e.g. a 2021 GLS for a 2018 car). Tight when the
# year is our only era clue; looser once a generation tag already pins the model
# (a generation can span ~7 years, so don't reject a late-run photo of it).
_YEAR_TOLERANCE = 3
_YEAR_TOLERANCE_WITH_GEN = 7


def _title_year(title: str) -> int | None:
    """A plausible model year mentioned in the file name, if any (1980-2039)."""
    for m in re.finditer(r"\b(19[89]\d|20[0-3]\d)\b", title):
        return int(m.group(1))
    return None


def _search(
    terms: str,
    *,
    require_landscape: bool,
    car_year: int | None = None,
    year_tolerance: int = _YEAR_TOLERANCE,
) -> str | None:
    """CC0-filtered Commons file search. Scans the top results and returns the
    first that is a real raster photo — landscape and wide enough when required,
    and (when car_year is given) within `year_tolerance` of the car's year — as a
    scaled thumbnail URL."""
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        # haslicense:unrestricted → only CC0 / public-domain files, so the result
        # never carries a watermark or an attribution requirement.
        "gsrsearch": f"haslicense:unrestricted {terms}",
        "gsrnamespace": "6",  # File: namespace
        "gsrlimit": "8",  # scan a few and pick the best-shaped one
        "prop": "imageinfo",
        "iiprop": "url|mime|size",
        "iiurlwidth": str(_THUMB_WIDTH),
    }
    try:
        resp = httpx.get(
            _COMMONS_API,
            params=params,
            headers={"User-Agent": _USER_AGENT},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        if not pages:
            return None
        # Search results keep their rank in `index`; honour it. Collect all the
        # acceptable ones, then prefer a front-view shot over the rest.
        ordered = sorted(pages.values(), key=lambda p: p.get("index", 0))
        acceptable: list[tuple[bool, str]] = []
        for page in ordered:
            info = (page.get("imageinfo") or [{}])[0]
            mime = info.get("mime", "")
            if not mime.startswith("image/") or "svg" in mime:
                continue
            title = page.get("title", "").lower()
            if any(bad in title for bad in _NAME_BLOCKLIST):
                continue  # motorsport / wreck / cutaway / interior / rear — skip
            w, h = info.get("width", 0), info.get("height", 0)
            if require_landscape and not (w > h and w >= _MIN_WIDTH):
                continue
            # A filename year far from the car's year → wrong generation.
            if car_year is not None:
                ty = _title_year(title)
                if ty is not None and abs(ty - car_year) > year_tolerance:
                    continue
            url = info.get("thumburl") or info.get("url")
            if not url:
                continue
            is_front = any(hint in title for hint in _FRONT_HINTS)
            acceptable.append((is_front, url))
        if not acceptable:
            return None
        # A front-hinted shot first; otherwise the top-ranked acceptable one.
        for is_front, url in acceptable:
            if is_front:
                return url
        return acceptable[0][1]
    except Exception:  # noqa: BLE001 — a car photo must never break a request
        logger.warning("Wikimedia car image resolve failed", exc_info=True)
        return None


def _slugify_brand(brand: str) -> str:
    """A car's brand → the dataset's slug convention: lower-case, spaces and
    other separators to hyphens (e.g. "Mercedes-Benz" → "mercedes-benz",
    "Alfa Romeo" → "alfa-romeo"). A Cyrillic marque maps to its Latin slug."""
    key = brand.strip().lower()
    if key in _BRAND_ALIASES:
        return _BRAND_ALIASES[key]
    out = []
    for ch in key:
        if ch.isascii() and ch.isalnum():
            out.append(ch)
        elif ch in " -_/":
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def brand_logo_url(brand: str | None) -> str | None:
    """A marque-logo URL for the brand, or None if it isn't in the set. No API
    call — a static CDN path gated on the known-slugs list."""
    if not brand:
        return None
    slug = _slugify_brand(brand)
    if slug not in LOGO_SLUGS:
        return None
    return _LOGO_CDN.format(slug=slug)
