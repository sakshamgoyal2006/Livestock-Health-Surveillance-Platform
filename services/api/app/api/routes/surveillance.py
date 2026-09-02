from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select

from app.api.deps import SessionDep, require_roles
from app.core.audit import append_audit
from app.domain.models import AlertEvent, HotspotCandidate, User
from app.operations.surveillance import refresh_hotspot_candidates, surveillance_aggregates
from app.schemas.checkpoint3 import AcknowledgeIn

router = APIRouter(prefix="/api/v1/surveillance", tags=["GIS surveillance"])
Officer = Annotated[User, Depends(require_roles("DISTRICT_OFFICER", "ADMIN"))]


@router.get("/aggregates")
async def aggregates(
    session: SessionDep,
    actor: Officer,
    level: str = Query(default="VILLAGE", pattern="^(VILLAGE|BLOCK|DISTRICT)$"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    species: str | None = None,
    syndrome: str | None = None,
    status: str | None = None,
    risk_tier: str | None = None,
) -> dict[str, Any]:
    del actor
    clock = date_to or datetime.now(UTC)
    values = await surveillance_aggregates(
        session,
        level=level,
        date_from=date_from or clock - timedelta(days=30),
        date_to=clock,
        species=species,
        syndrome=syndrome,
        status=status,
        risk_tier=risk_tier,
    )
    return {"privacy_minimum_count": 2, "items": values}


@router.post("/hotspots/refresh")
async def refresh(session: SessionDep, actor: Officer) -> dict[str, Any]:
    del actor
    rows = await refresh_hotspot_candidates(session)
    await session.commit()
    return {"detector_output": "CANDIDATE_ONLY", "count": len(rows)}


@router.get("/hotspots")
async def hotspots(session: SessionDep, actor: Officer) -> list[dict[str, Any]]:
    del actor
    rows = (
        await session.scalars(select(HotspotCandidate).order_by(HotspotCandidate.created_at.desc()))
    ).all()
    return [
        {
            "id": row.id,
            "area_name": row.area_name,
            "area_level": row.area_level,
            "status": row.status,
            "baseline_daily_rate": row.baseline_daily_rate,
            "observed_count": row.observed_count,
            "suspected_count": row.suspected_count,
            "vet_verified_count": row.vet_verified_count,
            "lab_confirmed_count": row.lab_confirmed_count,
            "confidence": row.confidence,
            "detector_version": row.detector_version,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "notice": "Hotspot candidate, not a confirmed outbreak",
        }
        for row in rows
    ]


@router.post("/hotspots/{candidate_id}/acknowledge")
async def acknowledge_hotspot(
    candidate_id: UUID, body: AcknowledgeIn, request: Request, session: SessionDep, actor: Officer
) -> dict[str, Any]:
    row = await session.get(HotspotCandidate, candidate_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "HOTSPOT_NOT_FOUND"})
    row.status = "ACKNOWLEDGED_CANDIDATE"
    row.acknowledged_by_user_id = actor.id
    row.acknowledged_at = datetime.now(UTC)
    row.reviewer_note = body.note
    event = await session.scalar(
        select(AlertEvent).where(AlertEvent.deduplication_key == f"hotspot:{row.candidate_key}")
    )
    if event:
        event.status = "ACKNOWLEDGED"
        event.acknowledged_by_user_id = actor.id
        event.acknowledged_at = row.acknowledged_at
    await append_audit(
        session,
        actor_user_id=actor.id,
        action="HOTSPOT_CANDIDATE_ACKNOWLEDGED",
        resource_type="hotspot_candidate",
        resource_id=row.id,
        request_id=request.state.request_id,
        details={"note": body.note or ""},
    )
    await session.commit()
    return {"id": row.id, "status": row.status}
