"""OCR.space fallback for receipts tesseract cannot read.

The free tier is 25k requests a month and needs no card — which is why it
exists here at all: Gemini's free tier turned out to be unavailable on an
account that has ever been attached to billing (`limit: 0`, not «exhausted»),
so a vision fallback that costs nothing had to come from somewhere else.

Engine 2 is used deliberately: it detects the language itself and reads
Ukrainian receipts, while engine 1 needs an explicit `language` and rejects
`ukr` outright.
"""

from __future__ import annotations

import base64
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_URL = "https://api.ocr.space/parse/image"
_TIMEOUT_SECONDS = 45
# Their public demo key, rate-limited but real: it keeps the fallback working
# out of the box, and a private key only raises the ceiling.
_DEMO_KEY = "helloworld"


def enabled() -> bool:
    return bool(settings.OCR_SPACE_API_KEY or settings.OCR_SPACE_USE_DEMO_KEY)


def recognize_text(image_bytes: bytes, content_type: str = "image/jpeg") -> str | None:
    """Return the text OCR.space reads on the image, or None on any failure."""
    if not enabled():
        return None

    payload = {
        "apikey": settings.OCR_SPACE_API_KEY or _DEMO_KEY,
        "base64Image": f"data:{content_type};base64,{base64.b64encode(image_bytes).decode()}",
        # Engine 2 auto-detects the language; engine 1 would need `language=ukr`,
        # which it does not accept.
        "OCREngine": "2",
        # Upscales small photos before reading — a phone shot of a receipt is
        # exactly the case it helps.
        "scale": "true",
    }
    try:
        response = httpx.post(_URL, data=payload, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError):
        logger.warning("OCR.space request failed", exc_info=True)
        return None

    if body.get("IsErroredOnProcessing"):
        logger.warning("OCR.space could not read the image: %s", body.get("ErrorMessage"))
        return None

    results = body.get("ParsedResults") or []
    if not results:
        return None
    return results[0].get("ParsedText") or None
