"""Telegram bot entrypoint (long polling): python -m app.bot.main"""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from app.bot.handlers import router
from app.bot.reminders import reminder_loop
from app.config import settings
from app.database import engine
from app.i18n import normalize_lang, t
from app.migrations import run_migrations


def bot_commands(lang: str) -> list[BotCommand]:
    """Command menu for Telegram, localized for ``lang`` (en default, uk)."""
    lang = normalize_lang(lang)
    return [
        BotCommand(command="start", description=t("bot.cmd.start", lang)),
        BotCommand(command="help", description=t("bot.cmd.help", lang)),
        BotCommand(command="status", description=t("bot.cmd.status", lang)),
        BotCommand(command="report", description=t("bot.cmd.report", lang)),
        BotCommand(command="note", description=t("bot.cmd.note", lang)),
        BotCommand(command="backup", description=t("bot.cmd.backup", lang)),
    ]


async def run() -> None:
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    # English is the default menu; Telegram serves the uk menu to uk clients.
    await bot.set_my_commands(bot_commands("en"))
    await bot.set_my_commands(bot_commands("uk"), language_code="uk")
    reminder_task = asyncio.create_task(reminder_loop(bot))
    try:
        await dispatcher.start_polling(bot)
    finally:
        reminder_task.cancel()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if not settings.TELEGRAM_BOT_TOKEN:
        print(
            "TELEGRAM_BOT_TOKEN не налаштовано — Telegram-бот не запущено. "
            "Додайте токен бота у файл .env і перезапустіть."
        )
        sys.exit(0)

    run_migrations(engine)
    asyncio.run(run())


if __name__ == "__main__":
    main()
