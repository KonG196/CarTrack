"""Account deletion, shared by the owner's own «delete my account» and the
superadmin panel's «delete this user» so the two can never drift apart.

Deleting an account removes every owned car and its whole history via the ORM
cascade (User.cars / User.memberships = all, delete-orphan), wipes the user's
upload directory, and orphans their authorship on OTHER people's shared cars —
because log_entries.author_id has no SET NULL FK on the migrated SQLite schema
and SQLite reuses freed integer ids, so a future signup could otherwise inherit
this id and be shown as the author of entries they never wrote.

Does NOT commit — the caller owns the transaction, so a panel delete and its
audit row land together.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.config import settings
from app.models import LogEntry, User

logger = logging.getLogger(__name__)


def purge_account(db: Session, user: User) -> None:
    """Remove a user and everything that belongs only to them. Best-effort on
    the on-disk files — a failed unlink must not strand the row, which is the
    record that actually authorises anything."""
    user_uploads = Path(settings.UPLOADS_DIR) / str(user.id)
    if user_uploads.exists():
        try:
            shutil.rmtree(user_uploads)
        except OSError as exc:
            logger.error("Failed to wipe uploads for user %s: %s", user.id, exc)
    db.execute(
        update(LogEntry).where(LogEntry.author_id == user.id).values(author_id=None)
    )
    db.delete(user)
