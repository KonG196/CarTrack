"""Database backups: hot SQLite copy / pg_dump, rotation, Telegram delivery.

CLI usage (for cron in production): python -m app.backup
"""

from __future__ import annotations

import asyncio
import datetime as dt
import gzip
import logging
import sqlite3
import subprocess
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile

from app.config import settings

logger = logging.getLogger(__name__)

BACKUP_PREFIX = "kapot_tracker-"


def _sqlite_path(database_url: str) -> Path:
    _, _, path = database_url.partition("///")
    if not path or ":memory:" in path:
        raise ValueError(f"Cannot back up a non-file SQLite database: {database_url}")
    return Path(path)


def create_backup(dest_dir: Path | None = None) -> Path:
    dest = Path(dest_dir) if dest_dir is not None else Path(settings.BACKUP_DIR)
    dest.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")

    if settings.DATABASE_URL.startswith("sqlite"):
        target = dest / f"{BACKUP_PREFIX}{stamp}.db"
        source = sqlite3.connect(_sqlite_path(settings.DATABASE_URL))
        try:
            copy = sqlite3.connect(target)
            try:
                source.backup(copy)
            finally:
                copy.close()
        finally:
            source.close()
        return target

    target = dest / f"{BACKUP_PREFIX}{stamp}.sql.gz"
    # pg_dump does not understand SQLAlchemy driver suffixes like +psycopg2.
    dsn = settings.DATABASE_URL.replace("+psycopg2", "", 1)
    dump = subprocess.run(
        ["pg_dump", "--dbname", dsn], check=True, capture_output=True
    )
    with gzip.open(target, "wb") as handle:
        handle.write(dump.stdout)
    return target


def rotate_backups(dest_dir: Path, keep: int = 14) -> int:
    backups = sorted(Path(dest_dir).glob(f"{BACKUP_PREFIX}*"), key=lambda p: p.name)
    stale = backups[:-keep] if keep > 0 else backups
    for path in stale:
        path.unlink()
    return len(stale)


async def send_backup_via_telegram(path: Path, bot: Bot | None = None) -> bool:
    """Send a backup file as a document to the admin backup chat.

    Returns False without touching the network when the chat id (or the bot
    token, for a fresh Bot) is not configured. The chat is admin-only: in
    hosted mode the backup contains every user's data.
    """
    if not settings.BACKUP_TELEGRAM_CHAT_ID:
        return False
    own_bot = bot is None
    if own_bot:
        if not settings.TELEGRAM_BOT_TOKEN:
            return False
        bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_document(
            chat_id=settings.BACKUP_TELEGRAM_CHAT_ID,
            document=FSInputFile(path),
            caption=f"Щоденний бекап Kapot Tracker: {path.name}",
        )
        return True
    finally:
        if own_bot:
            await bot.session.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    path = create_backup()
    deleted = rotate_backups(Path(settings.BACKUP_DIR), settings.BACKUP_KEEP)
    sent = asyncio.run(send_backup_via_telegram(path))
    logger.info(
        "Backup created: %s (rotated out %d, telegram %s)",
        path,
        deleted,
        "sent" if sent else "skipped",
    )


if __name__ == "__main__":
    main()
