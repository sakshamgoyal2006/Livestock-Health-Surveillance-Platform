from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import SessionDep, require_roles
from app.domain.models import HealthReport, User
from app.triage.contracts import TriageDecision, TriageJobResult
from app.triage.pipeline import latest_decision, run_report_triage

router = APIRouter(prefix="/api/v1", tags=["multimodal triage"])
TriageActor = Annotated[
    User, Depends(require_roles("FARMER", "FIELD_WORKER", "VETERINARIAN", "ADMIN"))
]
AssessmentReader = Annotated[
    User, Depends(require_roles("FARMER", "FIELD_WORKER", "VETERINARIAN", "ADMIN"))
]


def _can_access(report: HealthReport, actor: User) -> bool:
    return actor.role in {"VETERINARIAN", "ADMIN"} or report.reporter_user_id == actor.id


@router.post("/reports/{report_id}/triage", response_model=TriageJobResult)
async def retry_triage(
    report_id: UUID,
    request: Request,
    session: SessionDep,
    actor: TriageActor,
) -> TriageJobResult:
    report = await session.get(HealthReport, report_id)
    if report is None or not _can_access(report, actor):
        raise HTTPException(
            status_code=404,
            detail={"code": "REPORT_NOT_FOUND", "message": "Report was not found"},
        )
    return await run_report_triage(
        session,
        report.id,
        request_id=request.state.request_id,
        actor_user_id=actor.id,
        force_retry=True,
    )


@router.get("/reports/{report_id}/risk-assessment", response_model=TriageDecision)
async def get_risk_assessment(
    report_id: UUID, session: SessionDep, actor: AssessmentReader
) -> TriageDecision:
    report = await session.get(HealthReport, report_id)
    if report is None or not _can_access(report, actor):
        raise HTTPException(
            status_code=404,
            detail={"code": "REPORT_NOT_FOUND", "message": "Report was not found"},
        )
    decision = await latest_decision(session, report.id)
    if decision is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ASSESSMENT_NOT_READY",
                "message": "Preliminary triage is not available yet; retry is safe",
            },
        )
    return decision
