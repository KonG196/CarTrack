"""Daily loop: service-interval alerts, odometer nudge, weekly digest, backups."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from pathlib import Path

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app import backup
from app.bot import service
from app.config import settings
from app.database import SessionLocal

logger = logging.getLogger(__name__)

FIRST_RUN_DELAY_SECONDS = 60
RUN_PERIOD_SECONDS = 24 * 60 * 60
NUDGE_AFTER_DAYS = 7

# date.weekday(): Monday is 0, so Sunday is 6. The digest rides the daily pass
# rather than a scheduler of its own — six days out of seven it is a no-op, and
# that is cheaper than a second loop to keep alive.
DIGEST_WEEKDAY = 6

DONE_BUTTON = "Виконано"
SNOOZE_BUTTON = "Нагадати через 7 днів"

# Telegram truncates long button labels anyway; keep them readable instead.
_MAX_BUTTON_TITLE = 20


def _build_reminder_text(
    db, user, items: list[service.ReminderItem], today: dt.date
) -> str:
    lines = ["Нагадування Kapot Tracker: наближається або вже прострочене ТО."]
    last_car_id: int | None = None
    for item in items:
        if item.car.id != last_car_id:
            lines.append(
                f"\n{item.car.brand} {item.car.model} "
                f"(пробіг {item.car.current_odometer} км):"
            )
            last_car_id = item.car.id
        lines.append(service.format_interval_line(item.interval, item.computed))

    # Weekly odometer nudge: appended to the reminder only, never sent alone.
    latest = service.latest_log_date(db, user)
    if latest is None or (today - latest).days > NUDGE_AFTER_DAYS:
        lines.append(
            "\nІ ще: давно не було нових записів. Надішліть «пробіг 240054» "
            "— так прогнози будуть точнішими."
        )
    return "\n".join(lines)


def _short_title(title: str) -> str:
    if len(title) <= _MAX_BUTTON_TITLE:
        return title
    return f"{title[: _MAX_BUTTON_TITLE - 1].rstrip()}…"


def build_reminder_keyboard(items: list[service.ReminderItem]) -> InlineKeyboardMarkup:
    name_intervals = len(items) > 1
    rows = [
        [
            InlineKeyboardButton(
                text=(
                    f"{DONE_BUTTON}: {_short_title(item.interval.title)}"
                    if name_intervals
                    else DONE_BUTTON
                ),
                callback_data=f"done:{item.interval.id}",
            ),
            InlineKeyboardButton(
                text=SNOOZE_BUTTON, callback_data=f"snooze:{item.interval.id}"
            ),
        ]
        for item in items
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_due_reminders(bot: Bot) -> None:
    """One reminder pass over all linked users.

    Each user is isolated in try/except: a failed send (blocked bot, dead
    chat) must not prevent the remaining users from being notified, and the
    intervals are only stamped after a successful send.
    """
    today = dt.date.today()
    with SessionLocal() as db:
        for user, items in service.reminder_targets(db, today=today):
            try:
                text = _build_reminder_text(db, user, items, today)
                await bot.send_message(
                    chat_id=user.telegram_chat_id,
                    text=text,
                    reply_markup=build_reminder_keyboard(items),
                )
                service.stamp_notified(
                    db, [item.interval.id for item in items], today=today
                )
            except Exception:
                logger.exception("Failed to send reminders to user %s", user.id)


async def send_weekly_digests(bot: Bot, today: dt.date | None = None) -> None:
    """Sunday's digest pass: one message per car, to the car's owner.

    A no-op on the other six days, so the daily loop can call it every time
    without knowing what day it is.

    Each car is isolated in try/except rather than each user: a digest is one
    car's week and stands alone, so a blocked chat or an oversized message must
    not cost the owner their other cars' summaries. Nothing is stamped — the
    weekday is the schedule, and a digest that failed to send is simply lost
    rather than retried tomorrow (by tomorrow it would be last week's news).
    """
    if today is None:
        today = dt.date.today()
    if today.weekday() != DIGEST_WEEKDAY:
        return
    with SessionLocal() as db:
        for user, digests in service.digest_targets(db, today=today):
            for digest in digests:
                try:
                    await bot.send_message(
                        chat_id=user.telegram_chat_id, text=digest.text
                    )
                except Exception:
                    logger.exception(
                        "Failed to send the weekly digest for car %s to user %s",
                        digest.car.id,
                        user.id,
                    )


async def run_daily_backup(bot: Bot) -> None:
    """Create, rotate and deliver the daily backup; failures only get logged."""
    try:
        path = await asyncio.to_thread(backup.create_backup)
        await asyncio.to_thread(
            backup.rotate_backups, Path(settings.BACKUP_DIR), settings.BACKUP_KEEP
        )
        await backup.send_backup_via_telegram(path, bot=bot)
    except Exception:
        logger.exception("Daily backup failed")


async def reminder_loop(bot: Bot) -> None:
    await asyncio.sleep(FIRST_RUN_DELAY_SECONDS)
    while True:
        try:
            await send_due_reminders(bot)
        except Exception:
            logger.exception("Reminder pass failed")
        try:
            await send_weekly_digests(bot)
        except Exception:
            logger.exception("Weekly digest pass failed")
        await run_daily_backup(bot)
        await asyncio.sleep(RUN_PERIOD_SECONDS)
