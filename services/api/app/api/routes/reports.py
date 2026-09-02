from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func, select

from app.api.deps import SessionDep, require_roles
from app.domain.access import ActorIdentity, can_read_report
from app.domain.models import AuditLog, HealthReport, StatusHistory, User
from app.domain.sync import process_mutation
from app.schemas.common import SyncBatchResponse, SyncMutationResult
from app.schemas.reports import (
    ReportOut,
    ReportPayload,
    SyncBatchRequest,
    SyncMutationIn,
    TimelineEvent,
)
from app.triage.pipeline import latest_decision

router = APIRouter(prefix="/api/v1", tags=["reports and synchronization"])
Reporter = Annotated[User, Depends(require_roles("FARMER", "FIELD_WORKER"))]
CaseReader = Annotated[
    User, Depends(require_roles("FARMER", "FIELD_WORKER", "VETERINARIAN", "ADMIN"))
]
VetActor = Annotated[User, Depends(require_roles("VETERINARIAN", "ADMIN"))]


@router.post("/sync/batch", response_model=SyncBatchResponse)
async def sync_batch(
    body: SyncBatchRequest,
    request: Request,
    session: SessionDep,
    actor: Reporter,
) -> SyncBatchResponse:
    actor_identity = ActorIdentity(id=actor.id, role=actor.role)
    results: list[SyncMutationResult] = []
    for mutation in body.mutations:
        results.append(
            await process_mutation(
                session,
                actor=actor_identity,
                mutation=mutation,
                request_id=request.state.request_id,
            )
        )
    retry_needed = any(result.status in {"REJECTED", "CONFLICT"} for result in results)
    return SyncBatchResponse(
        results=results,
        server_time=datetime.now(UTC),
        next_retry_after_seconds=30 if retry_needed else None,
    )


@router.post("/reports", response_model=SyncMutationResult)
async def create_report_online(
    body: ReportPayload,
    request: Request,
    session: SessionDep,
    actor: Reporter,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=128)],
    client_mutation_id: Annotated[UUID, Header(alias="X-Client-Mutation-ID")],
) -> SyncMutationResult:
    actor_identity = ActorIdentity(id=actor.id, role=actor.role)
    mutation = SyncMutationIn(
        client_mutation_id=client_mutation_id,
        idempotency_key=idempotency_key,
        mutation_type="CREATE_REPORT",
        base_version=None,
        created_at_device=body.created_at_device,
        payload=body.model_dump(mode="json"),
    )
    return await process_mutation(
        session,
        actor=actor_identity,
        mutation=mutation,
        request_id=request.state.request_id,
    )


@router.get("/reports/{report_id}", response_model=ReportOut)
async def get_report(report_id: UUID, session: SessionDep, actor: CaseReader) -> ReportOut:
    report = await session.get(HealthReport, report_id)
    if report is None or not await can_read_report(session, actor, report.reporter_user_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "REPORT_NOT_FOUND", "message": "Report was not found"},
        )
    return ReportOut.model_validate(report)


@router.get("/reports/{report_id}/timeline", response_model=list[TimelineEvent])
async def report_timeline(
    report_id: UUID, session: SessionDep, actor: CaseReader
) -> list[TimelineEvent]:
    report = await session.get(HealthReport, report_id)
    if report is None or not await can_read_report(session, actor, report.reporter_user_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "REPORT_NOT_FOUND", "message": "Report was not found"},
        )
    status_rows = (
        await session.scalars(
            select(StatusHistory)
            .where(StatusHistory.health_report_id == report_id)
            .order_by(StatusHistory.created_at)
        )
    ).all()
    events = [
        TimelineEvent(
            occurred_at=row.created_at,
            event_type="STATUS_CHANGED",
            actor_user_id=row.actor_user_id,
            details={"from": row.from_status, "to": row.to_status, "reason": row.reason},
        )
        for row in status_rows
    ]
    return sorted(events, key=lambda event: event.occurred_at)


@router.get("/vet/cases", response_model=dict[str, object])
async def vet_cases(
    session: SessionDep,
    actor: VetActor,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, object]:
    del actor
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_PAGE", "message": "Invalid pagination values"},
        )
    base = select(HealthReport).where(HealthReport.status == "QUEUED_FOR_VET")
    total = await session.scalar(
        select(func.count())
        .select_from(HealthReport)
        .where(HealthReport.status == "QUEUED_FOR_VET")
    )
    reports = (
        await session.scalars(
            base.order_by(HealthReport.received_at_server.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = []
    for report in reports:
        item = ReportOut.model_validate(report).model_dump(mode="json")
        decision = await latest_decision(session, report.id)
        item["risk_assessment"] = decision.model_dump(mode="json") if decision else None
        items.append(item)
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total or 0,
        "clinical_notice": "Veterinary verification required; no diagnosis has been generated.",
    }


@router.get("/admin/audit", response_model=dict[str, object])
async def audit_viewer(
    session: SessionDep,
    actor: Annotated[User, Depends(require_roles("ADMIN"))],
    page: int = 1,
    page_size: int = 50,
) -> dict[str, object]:
    del actor
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(
            status_code=422, detail={"code": "INVALID_PAGE", "message": "Invalid page"}
        )
    total = await session.scalar(select(func.count()).select_from(AuditLog))
    rows = (
        await session.scalars(
            select(AuditLog)
            .order_by(AuditLog.occurred_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "occurred_at": row.occurred_at.isoformat(),
                "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
                "action": row.action,
                "resource_type": row.resource_type,
                "resource_id": str(row.resource_id) if row.resource_id else None,
                "request_id": row.request_id,
                "details": row.details,
                "entry_hash": row.entry_hash,
            }
            for row in rows
        ],
        "page": page,
        "page_size": page_size,
        "total": total or 0,
    }
