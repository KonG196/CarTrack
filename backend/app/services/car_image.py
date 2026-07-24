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
    "/logos/optimized/{slug}.png"
)

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


def _resolve(car: Car) -> str | None:
    """Find a CC0/public-domain Commons photo of this car. Returns a thumbnail
    URL or None. Tries make+model+year, then falls back to make+model."""
    terms = " ".join(str(p) for p in (car.brand, car.model, car.year) if p)
    url = _search(terms)
    if url is None and car.year:
        # A specific year may have no CC0 shot; the model without it often does.
        url = _search(f"{car.brand} {car.model}")
    return url


def _search(terms: str) -> str | None:
    """One CC0-filtered Commons file search; returns the top thumbnail URL."""
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        # haslicense:unrestricted → only CC0 / public-domain files, so the result
        # never carries a watermark or an attribution requirement.
        "gsrsearch": f"haslicense:unrestricted {terms}",
        "gsrnamespace": "6",  # File: namespace
        "gsrlimit": "1",
        "prop": "imageinfo",
        "iiprop": "url|mime",
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
        info = next(iter(pages.values())).get("imageinfo", [{}])[0]
        # Skip non-photo files (svg diagrams, etc.); prefer the scaled thumbnail.
        mime = info.get("mime", "")
        if mime and not mime.startswith("image/"):
            return None
        if "svg" in mime:
            return None
        return info.get("thumburl") or info.get("url") or None
    except Exception:  # noqa: BLE001 — a car photo must never break a request
        logger.warning("Wikimedia car image resolve failed", exc_info=True)
        return None


def _slugify_brand(brand: str) -> str:
    """A car's brand → the dataset's slug convention: lower-case, spaces and
    other separators to hyphens (e.g. "Mercedes-Benz" → "mercedes-benz",
    "Alfa Romeo" → "alfa-romeo")."""
    out = []
    for ch in brand.strip().lower():
        if ch.isalnum():
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
