from __future__ import annotations

import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AuditLog


async def append_audit(
    session: AsyncSession,
    *,
    actor_user_id: UUID | None,
    action: str,
    resource_type: str,
    resource_id: UUID | None,
    request_id: str,
    details: dict[str, object] | None = None,
) -> AuditLog:
    previous = await session.scalar(select(AuditLog).order_by(AuditLog.occurred_at.desc()).limit(1))
    previous_hash = previous.entry_hash if previous else None
    safe_details = details or {}
    canonical = json.dumps(
        {
            "previous_hash": previous_hash,
            "actor_user_id": str(actor_user_id) if actor_user_id else None,
            "action": action,
            "resource_type": resource_type,
            "resource_id": str(resource_id) if resource_id else None,
            "request_id": request_id,
            "details": safe_details,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id,
        details=safe_details,
        previous_hash=previous_hash,
        entry_hash=hashlib.sha256(canonical.encode()).hexdigest(),
    )
    session.add(entry)
    return entry
