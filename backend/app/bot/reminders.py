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


#: The fuel a spike is about, in the genitive so it reads «стрибок витрати газу».
_FUEL_WORD = {
    "petrol": "бензину",
    "diesel": "дизеля",
    "lpg": "газу",
    "electric": "електрики",
    "hybrid": "пального",
}


def _build_consumption_text(alert: service.ConsumptionAlert) -> str:
    car = alert.car
    spike = alert.spike
    fuel = _FUEL_WORD.get(spike.fuel_kind, "пального")
    return (
        f"⛽ {car.brand} {car.model}: помічено стрибок витрати {fuel} на "
        f"{spike.pct_over}% — {spike.consumption_l_100km:.1f} л/100 км проти "
        f"звичних ~{spike.baseline_l_100km:.1f}.\n"
        "Якщо стиль їзди не змінювався, варто перевірити тиск у шинах, а також "
        "стан сажового фільтра чи свічок."
    )


async def send_consumption_alerts(bot: Bot) -> None:
    """One watchdog pass: warn each owner about a fresh consumption spike.

    Each owner is isolated in try/except, and the spike is stamped on the car
    only after a successful send — a blocked chat must not silence the warning
    for good, and a failed send is retried next pass.
    """
    with SessionLocal() as db:
        for user, alert in service.consumption_alert_targets(db):
            try:
                await bot.send_message(
                    chat_id=user.telegram_chat_id,
                    text=_build_consumption_text(alert),
                )
                service.stamp_consumption_alert(db, alert.car, alert.spike.log_id)
            except Exception:
                logger.exception(
                    "Failed to send consumption alert to user %s", user.id
                )


def _build_seasonal_text(reminder: service.SeasonalReminder) -> str:
    car = reminder.car
    if reminder.kind == "tires":
        return (
            f"🛞 {car.brand} {car.model}: наближається зима, а на авто досі літня "
            "гума. Варто записатися на шиномонтаж, поки немає двотижневих черг."
        )
    return (
        "🥶 Наближаються перші нічні заморозки у вашому регіоні. Не забудьте "
        "вибризкати літню воду й залити зимову рідину (-20 °C), щоб не розірвало "
        "трубки й моторчик омивача скла."
    )


async def send_seasonal_reminders(bot: Bot) -> None:
    """One autumn pass: winter-tyre and winter-washer nudges, once per season.

    Each owner is isolated in try/except, and the year is stamped on the car
    only after a successful send — a blocked chat must not burn the season's
    single reminder, and a failed send is retried on the next daily pass.
    """
    today = dt.date.today()
    with SessionLocal() as db:
        for user, reminder in service.seasonal_reminder_targets(db, today=today):
            try:
                await bot.send_message(
                    chat_id=user.telegram_chat_id,
                    text=_build_seasonal_text(reminder),
                )
                service.stamp_seasonal(db, reminder.car, reminder.kind, today.year)
            except Exception:
                logger.exception(
                    "Failed to send seasonal reminder to user %s", user.id
                )


_SEASON_WORD = {"summer": "літній", "winter": "зимовий", "all_season": "всесезонний"}


def _build_rotation_text(reminder: service.RotationReminder) -> str:
    car = reminder.car
    season = _SEASON_WORD.get(reminder.tire_set.season, "")
    which = f"{season} комплект шин".strip()
    return (
        f"🛞 {car.brand} {car.model}: {which} проїхав уже "
        f"{reminder.km_since_rotation} км від останньої ротації. Рекомендовано "
        "переставити колеса місцями (задню вісь наперед), щоб протектор "
        "зношувався рівномірно. Зробили — тапніть кнопку нижче."
    )


def build_rotation_keyboard(tire_set_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛞 Зробити ротацію", callback_data=f"rotate:{tire_set_id}"
                )
            ]
        ]
    )


async def send_rotation_reminders(bot: Bot) -> None:
    """One pass: nudge owners whose tyres are due an axle rotation.

    Isolated per owner; the 10k mark is stamped on the set only after a
    successful send, so a blocked chat is retried and never double-counts.
    """
    with SessionLocal() as db:
        for user, reminder in service.rotation_reminder_targets(db):
            try:
                await bot.send_message(
                    chat_id=user.telegram_chat_id,
                    text=_build_rotation_text(reminder),
                    reply_markup=build_rotation_keyboard(reminder.tire_set.id),
                )
                service.stamp_rotation(db, reminder.tire_set, reminder.due_km)
            except Exception:
                logger.exception(
                    "Failed to send rotation reminder to user %s", user.id
                )


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


def _backed_up_today() -> bool:
    """Whether a backup for today already exists on disk.

    The loop starts sixty seconds after the process does, so a day of deploys
    used to mean a dump in the chat per restart. The dated filenames are the
    record — no extra state to keep in sync.
    """
    stamp = dt.date.today().strftime("%Y%m%d")
    directory = Path(settings.BACKUP_DIR)
    if not directory.exists():
        return False
    return any(stamp in item.name for item in directory.iterdir() if item.is_file())


async def run_daily_backup(bot: Bot, force: bool = False) -> None:
    """Create, rotate and deliver the daily backup; failures only get logged."""
    if not force and _backed_up_today():
        logger.info("Backup for today already exists, skipping")
        return
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
            await send_consumption_alerts(bot)
        except Exception:
            logger.exception("Consumption watchdog pass failed")
        try:
            await send_seasonal_reminders(bot)
        except Exception:
            logger.exception("Seasonal reminder pass failed")
        try:
            await send_rotation_reminders(bot)
        except Exception:
            logger.exception("Rotation reminder pass failed")
        try:
            await send_weekly_digests(bot)
        except Exception:
            logger.exception("Weekly digest pass failed")
        # Backups are on-demand now (bot /backup, admin-only; or the app's data
        # export) — no daily auto-push into the chat. run_daily_backup stays for
        # the /backup command and the `python -m app.backup` CLI.
        await asyncio.sleep(RUN_PERIOD_SECONDS)
