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
from app.migrations import run_migrations

# Published to Telegram's command menu on startup.
BOT_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="Прив'язати акаунт Kapot Tracker"),
    BotCommand(command="help", description="Довідка та формати повідомлень"),
    BotCommand(command="status", description="Стан авто та найближчі ТО"),
    BotCommand(command="report", description="PDF-звіт по авто"),
]


async def run() -> None:
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    await bot.set_my_commands(BOT_COMMANDS)
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
