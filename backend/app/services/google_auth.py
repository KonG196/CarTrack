"""Verify Google Sign-In ID tokens.

The frontend (Google Identity Services) hands the browser an ID token — a JWT
signed by Google. We check its signature against Google's public keys and that
its audience is our client id, then trust the claims it carries (email, whether
Google verified that email, and the stable Google user id).

Verification is on only when GOOGLE_CLIENT_ID is set; otherwise the endpoint is
disabled and this raises GoogleAuthUnavailable.
"""

from __future__ import annotations

from dataclasses import dataclass

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.config import settings

# Google's ID tokens are always issued by one of these.
_ISSUERS = ("https://accounts.google.com", "accounts.google.com")


class GoogleAuthUnavailable(Exception):
    """No GOOGLE_CLIENT_ID configured — Google sign-in is turned off."""


class GoogleAuthError(Exception):
    """The ID token was missing, malformed, or failed verification."""


@dataclass(frozen=True)
class GoogleIdentity:
    email: str
    email_verified: bool
    sub: str  # Google's stable, unique user id


def verify_id_token(token: str) -> GoogleIdentity:
    """Verify a Google ID token and return its identity, or raise.

    Raises GoogleAuthUnavailable when sign-in is off, GoogleAuthError on any
    bad/forged/expired token or a claim that doesn't check out.
    """
    client_id = settings.GOOGLE_CLIENT_ID.strip()
    if not client_id:
        raise GoogleAuthUnavailable()

    try:
        claims = google_id_token.verify_oauth2_token(
            token, google_requests.Request(), client_id
        )
    except (ValueError, GoogleAuthError) as exc:  # library raises ValueError on failure
        raise GoogleAuthError(str(exc)) from exc

    if claims.get("iss") not in _ISSUERS:
        raise GoogleAuthError("unexpected token issuer")

    email = claims.get("email")
    sub = claims.get("sub")
    if not email or not sub:
        raise GoogleAuthError("token missing email or subject")

    return GoogleIdentity(
        email=email.strip().lower(),
        email_verified=bool(claims.get("email_verified", False)),
        sub=str(sub),
    )
