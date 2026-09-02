from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from app.api.deps import SessionDep, require_roles
from app.core.audit import append_audit
from app.domain.models import AlertEvent, NotificationOutbox, User
from app.operations.alerts import process_outbox_item
from app.schemas.checkpoint3 import AcknowledgeIn

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts and outbox"])
AlertActor = Annotated[User, Depends(require_roles("DISTRICT_OFFICER", "ADMIN"))]


@router.get("")
async def list_alerts(session: SessionDep, actor: AlertActor) -> list[dict[str, Any]]:
    del actor
    rows = (await session.scalars(select(AlertEvent).order_by(AlertEvent.created_at.desc()))).all()
    return [
        {
            "id": row.id,
            "type": row.alert_type,
            "status": row.status,
            "context": row.context,
            "escalation_level": row.escalation_level,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.post("/outbox/process")
async def process_outbox(session: SessionDep, actor: AlertActor) -> dict[str, int]:
    del actor
    rows = (
        await session.scalars(
            select(NotificationOutbox).where(
                NotificationOutbox.status.in_(["PENDING", "RETRY_PENDING", "RATE_LIMITED"])
            )
        )
    ).all()
    for row in rows:
        await process_outbox_item(session, row)
    await session.commit()
    return {"processed": len(rows), "external_messages_sent": 0}


@router.post("/{alert_id}/acknowledge")
async def acknowledge(
    alert_id: UUID, body: AcknowledgeIn, request: Request, session: SessionDep, actor: AlertActor
) -> dict[str, Any]:
    row = await session.get(AlertEvent, alert_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "ALERT_NOT_FOUND"})
    row.status = "ACKNOWLEDGED"
    row.acknowledged_by_user_id = actor.id
    row.acknowledged_at = datetime.now(UTC)
    outbox = (
        await session.scalars(
            select(NotificationOutbox).where(NotificationOutbox.alert_event_id == row.id)
        )
    ).all()
    for item in outbox:
        item.status = "ACKNOWLEDGED"
    await append_audit(
        session,
        actor_user_id=actor.id,
        action="ALERT_ACKNOWLEDGED",
        resource_type="alert_event",
        resource_id=row.id,
        request_id=request.state.request_id,
        details={"note": body.note or ""},
    )
    await session.commit()
    return {"id": row.id, "status": row.status}
