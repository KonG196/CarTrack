"""Daily reminder loop: service-interval alerts plus an odometer nudge."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging

from aiogram import Bot

from app.bot import service
from app.database import SessionLocal

logger = logging.getLogger(__name__)

FIRST_RUN_DELAY_SECONDS = 60
RUN_PERIOD_SECONDS = 24 * 60 * 60
NUDGE_AFTER_DAYS = 7


def _build_reminder_text(
    db, user, items: list[service.ReminderItem], today: dt.date
) -> str:
    """Aggregate one Ukrainian reminder message for a user."""
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
            "\nІ ще: давно не було нових записів. Надішліть поточний пробіг "
            "простим числом — так прогнози будуть точнішими."
        )
    return "\n".join(lines)


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
                await bot.send_message(chat_id=user.telegram_chat_id, text=text)
                service.stamp_notified(
                    db, [item.interval.id for item in items], today=today
                )
            except Exception:
                logger.exception("Failed to send reminders to user %s", user.id)


async def reminder_loop(bot: Bot) -> None:
    """Run reminder passes forever: first after ~60s, then every 24 hours."""
    await asyncio.sleep(FIRST_RUN_DELAY_SECONDS)
    while True:
        try:
            await send_due_reminders(bot)
        except Exception:
            logger.exception("Reminder pass failed")
        await asyncio.sleep(RUN_PERIOD_SECONDS)
