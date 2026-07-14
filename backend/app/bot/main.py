"""Telegram bot entrypoint (long polling): python -m app.bot.main"""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher

from app.bot.handlers import router
from app.bot.reminders import reminder_loop
from app.config import settings
from app.database import Base, engine
from app.migrations import ensure_schema


async def run() -> None:
    """Start long polling with the reminder loop as a background task."""
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    reminder_task = asyncio.create_task(reminder_loop(bot))
    try:
        await dispatcher.start_polling(bot)
    finally:
        reminder_task.cancel()


def main() -> None:
    """Validate configuration, prepare the schema and run the bot."""
    logging.basicConfig(level=logging.INFO)
    if not settings.TELEGRAM_BOT_TOKEN:
        print(
            "TELEGRAM_BOT_TOKEN не налаштовано — Telegram-бот не запущено. "
            "Додайте токен бота у файл .env і перезапустіть."
        )
        sys.exit(0)

    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)
    asyncio.run(run())


if __name__ == "__main__":
    main()
