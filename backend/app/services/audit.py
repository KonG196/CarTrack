"""Recording superadmin actions to admin_audit_log.

One helper, `record`, that both self-describes the action and captures who it was
aimed at — including the target's email verbatim, so the row stays readable after
the target account is deleted (the FK goes to NULL, the string does not). The
caller must commit; record only stages the row, so the action and its audit entry
land in the same transaction (both or neither).
"""

from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.models import AdminAuditLog, User


def record(
    db: Session,
    *,
    actor: User,
    action: str,
    target: Optional[User] = None,
    detail: Optional[dict] = None,
) -> AdminAuditLog:
    """Stage one audit row. Does NOT commit — the caller owns the transaction."""
    entry = AdminAuditLog(
        actor_id=actor.id,
        action=action,
        target_user_id=target.id if target else None,
        target_email=target.email if target else None,
        detail=json.dumps(detail, ensure_ascii=False) if detail else None,
    )
    db.add(entry)
    return entry
