"""The public QR passport: token minting, its URL, and a printable QR SVG."""

from __future__ import annotations

import uuid

import segno

from app.config import settings


def new_token() -> str:
    """An unguessable 32-hex-char token for a passport link."""
    return uuid.uuid4().hex


def passport_url(token: str) -> str:
    """The public page a QR points at, off the configured public base URL."""
    return f"{settings.PUBLIC_URL.rstrip('/')}/p/{token}"


def qr_svg(url: str) -> str:
    """An inline SVG QR of the URL — embedded straight into the page, no image
    request and no client-side QR library. Dark modules on transparent, so it
    reads on paper and on screen alike."""
    qr = segno.make(url, error="m")
    return qr.svg_inline(scale=4, border=2, dark="#111827")
