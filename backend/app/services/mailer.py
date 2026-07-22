"""Outgoing email over plain SMTP.

Sending is optional on purpose: with no SMTP_HOST the app must stay fully
usable offline, so callers treat a False return as "no mail was sent" rather
than an error. Whether that is acceptable is the caller's decision — the
registration flow, for one, auto-verifies instead of stranding the account.

Every letter goes out as multipart/alternative: a plain-text part (the source
of truth, and what clients that block HTML or images fall back to) plus a
branded HTML part in the app's dark-garage/amber style. The HTML is built with
tables and inline styles only — the lowest common denominator that Gmail,
Outlook and Apple Mail all render.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from app.config import settings
from app.i18n import normalize_lang, t

logger = logging.getLogger(__name__)

# The logo travels inside the letter as an inline (CID) image rather than an
# external URL: external images are blocked by default in Gmail and would need
# PUBLIC_URL to be publicly reachable, while a CID image shows on its own and
# works even before the app has a public domain.
_LOGO_CID = "kapotlogo"
_LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "email-logo.png"


def _read_logo() -> Optional[bytes]:
    try:
        return _LOGO_PATH.read_bytes()
    except OSError:
        logger.warning("Email logo not found at %s", _LOGO_PATH)
        return None

# Brand tokens, mirrored from the frontend design system (tailwind.config.js).
_GARAGE = "#0B1119"
_PANEL = "#121A26"
_RAISED = "#0D1520"
_EDGE = "#1D2A3E"
_FG = "#E9EEF6"
_MIST = "#93A1B8"
_MUTED = "#6B7A90"
_AMBER = "#FFB454"
_AMBER_INK = "#231708"

_SANS = "Arial, Helvetica, sans-serif"
_MONO = "'Courier New', Consolas, monospace"


def mail_enabled() -> bool:
    return bool(settings.SMTP_HOST)


def send_mail(to: str, subject: str, body: str, html: Optional[str] = None) -> bool:
    """Send a message. Returns False when mail is off or fails.

    `body` is the plain-text part; when `html` is given the letter is sent as
    multipart/alternative so text-only clients still get a readable message.
    """
    if not mail_enabled():
        logger.info("SMTP disabled, would send to %s: %s", to, subject)
        return False

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype="html")
        logo = _read_logo()
        if logo:
            # The html part becomes multipart/related, holding the image the
            # HTML references as cid:kapotlogo.
            html_part = message.get_payload()[1]
            html_part.add_related(
                logo, maintype="image", subtype="png", cid=f"<{_LOGO_CID}>"
            )

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
            if settings.SMTP_STARTTLS:
                smtp.starttls()
            if settings.SMTP_USER:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(message)
        return True
    except (smtplib.SMTPException, OSError):
        # A dead mail server must not take the request down with it: the caller
        # decides what an unsent letter means.
        logger.exception("SMTP send to %s failed", to)
        return False


def _render_email(
    *,
    lang: str = "en",
    heading: str,
    lede: str,
    code: Optional[str] = None,
    button: Optional[tuple[str, str]] = None,
    note: Optional[str] = None,
) -> str:
    """Build the branded HTML letter. `button` is (label, url)."""
    lang = normalize_lang(lang)
    code_block = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin:0 0 20px;"><tr><td align="center" '
        f'style="background:{_RAISED};border:1px solid {_EDGE};border-radius:12px;padding:18px;">'
        f'<div style="font-family:{_MONO};font-size:30px;font-weight:700;'
        f'letter-spacing:8px;color:{_AMBER};">{code}</div></td></tr></table>'
        if code
        else ""
    )
    button_block = ""
    if button:
        label, url = button
        button_block = (
            # A full-width wrapper cell centres the button; the inner table keeps
            # the pill tight around its label.
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin:6px 0 14px;"><tr><td align="center">'
            f'<table role="presentation" cellpadding="0" cellspacing="0"><tr>'
            f'<td align="center" style="border-radius:10px;background:{_AMBER};">'
            f'<a href="{url}" style="display:inline-block;padding:13px 30px;'
            f'font-family:{_SANS};font-weight:700;font-size:15px;color:{_AMBER_INK};'
            f'text-decoration:none;">{label}</a>'
            f'</td></tr></table></td></tr></table>'
            # Direct-link fallback: if the client strips the styled button, the
            # raw URL is still there to copy.
            f'<p style="margin:0 0 20px;font-size:13px;line-height:1.6;color:{_MIST};'
            f'font-family:{_SANS};text-align:center;">{t("email.button_fallback", lang)}<br>'
            f'<a href="{url}" style="color:{_AMBER};word-break:break-all;'
            f'text-decoration:underline;">{url}</a></p>'
        )
    note_block = (
        f'<p style="margin:0;font-size:13px;line-height:1.6;color:{_MUTED};'
        f'font-family:{_SANS};">{note}</p>'
        if note
        else ""
    )

    return f"""\
<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark light">
<meta name="supported-color-schemes" content="dark light">
<title>Kapot Tracker</title>
</head>
<body style="margin:0;padding:0;background:{_GARAGE};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_GARAGE};">
  <tr><td align="center" style="padding:32px 16px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
      style="max-width:480px;background:{_PANEL};border:1px solid {_EDGE};border-radius:16px;">
      <tr><td style="padding:24px 28px 6px;">
        <table role="presentation" cellpadding="0" cellspacing="0"><tr>
          <td style="vertical-align:middle;padding-right:11px;">
            <img src="cid:{_LOGO_CID}" width="50" height="40" alt=""
              style="display:block;"></td>
          <td style="vertical-align:middle;font-family:{_SANS};font-weight:700;
            font-size:17px;letter-spacing:.4px;"><span
            style="color:{_AMBER};vertical-align:middle;">KAPOT</span><span
            style="font-size:11px;letter-spacing:1.6px;color:{_MIST};padding-left:6px;vertical-align:middle;">TRACKER</span></td>
        </tr></table>
      </td></tr>
      <tr><td style="padding:14px 28px 6px;font-family:{_SANS};">
        <h1 style="margin:0 0 10px;font-size:20px;font-weight:700;color:{_FG};">{heading}</h1>
        <p style="margin:0 0 20px;font-size:15px;line-height:1.65;color:{_MIST};">{lede}</p>
        {code_block}{button_block}{note_block}
      </td></tr>
      <tr><td style="padding:20px 28px 26px;border-top:1px solid {_EDGE};">
        <p style="margin:0;font-size:12px;line-height:1.5;color:{_MUTED};
          font-family:{_SANS};">{t("email.footer", lang)}</p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>"""


def send_email_change(to: str, code: str, lang: str = "en") -> bool:
    """The code goes to the NEW address, which is the whole point of the flow:
    only someone who can read that inbox can move the account to it."""
    lang = normalize_lang(lang)
    hours = settings.VERIFY_CODE_EXPIRE_HOURS
    return send_mail(
        to,
        t("email.change.subject", lang),
        t("email.change.text", lang, code=code, hours=hours),
        html=_render_email(
            lang=lang,
            heading=t("email.change.heading", lang),
            lede=t("email.change.lede", lang),
            code=code,
            note=t("email.change.note", lang, hours=hours),
        ),
    )


def send_verification(to: str, code: str, lang: str = "en") -> bool:
    lang = normalize_lang(lang)
    hours = settings.VERIFY_CODE_EXPIRE_HOURS
    link = f"{settings.PUBLIC_URL.rstrip('/')}/verify?email={to}&code={code}"
    return send_mail(
        to,
        t("email.verify.subject", lang),
        t("email.verify.text", lang, code=code, link=link, hours=hours),
        html=_render_email(
            lang=lang,
            heading=t("email.verify.heading", lang),
            lede=t("email.verify.lede", lang),
            code=code,
            button=(t("email.verify.button", lang), link),
            note=t("email.verify.note", lang, hours=hours),
        ),
    )


def send_reset_code_mail(to: str, code: str, lang: str = "en") -> bool:
    # Magic link: /reset prefills the code and jumps straight to the
    # new-password step, so the letter is one click from resetting.
    lang = normalize_lang(lang)
    link = f"{settings.PUBLIC_URL.rstrip('/')}/reset?email={to}&code={code}"
    return send_mail(
        to,
        t("email.reset.subject", lang),
        t("email.reset.text", lang, code=code, link=link),
        html=_render_email(
            lang=lang,
            heading=t("email.reset.heading", lang),
            lede=t("email.reset.lede", lang),
            code=code,
            button=(t("email.reset.button", lang), link),
            note=t("email.reset.note", lang),
        ),
    )
