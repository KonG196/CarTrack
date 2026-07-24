"""Bot admin mode: owner-only paginated views of users, cars and DB stats.

The admin Telegram integration elsewhere is outbound-only, so these live in the
main user bot instead. Access is gated by ``User.is_superadmin`` in the handler;
this module only holds the (in-memory) mode flag, the inline keyboards, and the
message formatters. Formatters take already-fetched, safe objects and never
read sensitive columns.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.orm import Session

from app.bot import service
from app.i18n import t
from app.models import Car, User

# Rows per page. One definition, used everywhere.
_ADMIN_PAGE = 20

# Chats currently in admin mode. In-memory on purpose: the flag is trivial to
# rebuild (send /admin again) and resets safely to "off" on restart.
_admin_chats: set[int] = set()


def is_admin_mode(chat_id: int) -> bool:
    return chat_id in _admin_chats


def set_admin_mode(chat_id: int, on: bool) -> None:
    if on:
        _admin_chats.add(chat_id)
    else:
        _admin_chats.discard(chat_id)


def menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("bot.admin.btnUsers", lang), callback_data="adm:users:0"
                ),
                InlineKeyboardButton(
                    text=t("bot.admin.btnCars", lang), callback_data="adm:cars:0"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t("bot.admin.btnStats", lang), callback_data="adm:stats:0"
                ),
                InlineKeyboardButton(
                    text=t("bot.admin.btnClose", lang), callback_data="adm:close:0"
                ),
            ],
        ]
    )


def page_keyboard(kind: str, page: int, pages: int, lang: str) -> InlineKeyboardMarkup:
    """Nav row for a list: ◀ (if not first), ▶ (if not last), then a menu button.

    ``page`` is 1-based here (as shown to the user); callback data carries the
    0-based index of the target page.
    """
    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(
            InlineKeyboardButton(
                text=t("bot.admin.prev", lang),
                callback_data=f"adm:{kind}:{page - 2}",
            )
        )
    if page < pages:
        nav.append(
            InlineKeyboardButton(
                text=t("bot.admin.next", lang),
                callback_data=f"adm:{kind}:{page}",
            )
        )
    rows: list[list[InlineKeyboardButton]] = []
    if nav:
        rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton(
                text=t("bot.admin.menuTitle", lang), callback_data="adm:menu:0"
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _pages(total: int) -> int:
    """How many pages ``total`` rows span (at least 1, so an empty list shows 1/1)."""
    return max(1, (total + _ADMIN_PAGE - 1) // _ADMIN_PAGE)


def _footer(page: int, pages: int, total: int, lang: str) -> str:
    return t("bot.admin.pageFooter", lang, page=page, pages=pages, total=total)


def format_users(
    db: Session,
    users: list[User],
    page: int,
    pages: int,
    total: int,
    lang: str,
) -> str:
    title = t("bot.admin.usersTitle", lang)
    if not users:
        return f"{title}\n\n{t('bot.admin.empty', lang)}"
    lines = []
    for u in users:
        verified = " ✅" if u.email_verified else ""
        provider = u.auth_provider or "password"
        cars = service.admin_user_car_count(db, u.id)
        joined = u.created_at.date().isoformat() if u.created_at else "—"
        lines.append(
            t(
                "bot.admin.userRow",
                lang,
                id=u.id,
                email=u.email,
                provider=provider,
                verified=verified,
                cars=cars,
                joined=joined,
            )
        )
    body = "\n".join(lines)
    return f"{title}\n\n{body}\n\n{_footer(page, pages, total, lang)}"


def format_cars(
    cars: list[Car],
    page: int,
    pages: int,
    total: int,
    lang: str,
) -> str:
    title = t("bot.admin.carsTitle", lang)
    if not cars:
        return f"{title}\n\n{t('bot.admin.empty', lang)}"
    lines = []
    for c in cars:
        label = " ".join(part for part in (c.brand, c.model) if part)
        lines.append(
            t(
                "bot.admin.carRow",
                lang,
                id=c.id,
                label=label,
                year=c.year,
                odo=c.current_odometer,
                owner=c.user_id,
            )
        )
    body = "\n".join(lines)
    return f"{title}\n\n{body}\n\n{_footer(page, pages, total, lang)}"


def format_stats(stats: dict, lang: str) -> str:
    title = t("bot.admin.statsTitle", lang)
    body = t(
        "bot.admin.statsBody",
        lang,
        users=stats["users"],
        verified=stats["verified_users"],
        telegram=stats["users_with_telegram"],
        cars=stats["cars"],
        logs=stats["log_entries"],
    )
    return f"{title}\n\n{body}"
