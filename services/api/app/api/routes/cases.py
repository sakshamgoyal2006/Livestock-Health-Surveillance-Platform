from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from app.api.deps import SessionDep, require_roles
from app.core.audit import append_audit
from app.domain.models import (
    CaseFollowUp,
    LabReferral,
    User,
    VeterinaryCase,
)
from app.operations.alerts import enqueue_alert
from app.operations.cases import (
    add_follow_up,
    assign_case,
    case_evidence,
    record_lab_result,
    record_vet_review,
    request_sample,
    transition_case,
)
from app.schemas.checkpoint3 import (
    AssignCaseIn,
    EscalateIn,
    FollowUpIn,
    LabResultIn,
    SampleRequestIn,
    TransitionCaseIn,
    VetReviewIn,
)

router = APIRouter(prefix="/api/v1", tags=["veterinarian case management"])
Vet = Annotated[User, Depends(require_roles("VETERINARIAN", "ADMIN"))]


def _error(exc: ValueError) -> HTTPException:
    code = str(exc)
    status = 409 if code in {"STALE_CASE_VERSION", "INVALID_CASE_TRANSITION"} else 403
    if code in {"REPORT_NOT_FOUND", "CASE_EVIDENCE_INCOMPLETE"}:
        status = 404
    if code.startswith("INVALID_"):
        status = 422
    return HTTPException(
        status_code=status, detail={"code": code, "message": code.replace("_", " ").title()}
    )


async def _case(session: SessionDep, case_id: UUID) -> VeterinaryCase:
    row = await session.get(VeterinaryCase, case_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "CASE_NOT_FOUND"})
    return row


def _summary(row: VeterinaryCase) -> dict[str, Any]:
    return {
        "id": row.id,
        "health_report_id": row.health_report_id,
        "state": row.state,
        "assigned_veterinarian_user_id": row.assigned_veterinarian_user_id,
        "suspected_label": row.suspected_label,
        "suspected_status": row.suspected_status,
        "verified_label": row.verified_label,
        "verified_status": row.verified_status,
        "lab_status": row.lab_status,
        "escalated": row.escalated,
        "escalation_level": row.escalation_level,
        "version": row.version,
        "created_at": row.created_at,
    }


@router.get("/vet/operational-cases")
async def list_cases(session: SessionDep, actor: Vet) -> list[dict[str, Any]]:
    query = select(VeterinaryCase).order_by(VeterinaryCase.created_at.desc())
    if actor.role == "VETERINARIAN":
        query = query.where(
            (VeterinaryCase.assigned_veterinarian_user_id.is_(None))
            | (VeterinaryCase.assigned_veterinarian_user_id == actor.id)
        )
    return [_summary(row) for row in (await session.scalars(query)).all()]


@router.get("/vet/cases/{case_id}")
async def get_case(case_id: UUID, session: SessionDep, actor: Vet) -> dict[str, Any]:
    row = await _case(session, case_id)
    try:
        from app.operations.cases import ensure_case_access

        ensure_case_access(row, actor)
        return await case_evidence(session, row)
    except ValueError as exc:
        raise _error(exc) from exc


@router.post("/vet/cases/{case_id}/assign")
async def assign(
    case_id: UUID, body: AssignCaseIn, request: Request, session: SessionDep, actor: Vet
) -> dict[str, Any]:
    row = await _case(session, case_id)
    veterinarian = await session.get(User, body.veterinarian_user_id or actor.id)
    if veterinarian is None:
        raise HTTPException(status_code=422, detail={"code": "INVALID_VETERINARIAN"})
    try:
        await assign_case(
            session,
            case=row,
            actor=actor,
            veterinarian=veterinarian,
            expected_version=body.expected_version,
            request_id=request.state.request_id,
        )
        await session.commit()
        return _summary(row)
    except ValueError as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.post("/vet/cases/{case_id}/transition")
async def transition(
    case_id: UUID, body: TransitionCaseIn, request: Request, session: SessionDep, actor: Vet
) -> dict[str, Any]:
    row = await _case(session, case_id)
    try:
        await transition_case(
            session,
            case=row,
            actor=actor,
            to_state=body.to_state,
            reason=body.reason,
            request_id=request.state.request_id,
            expected_version=body.expected_version,
        )
        await session.commit()
        return _summary(row)
    except ValueError as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.post("/vet/cases/{case_id}/review")
async def review(
    case_id: UUID, body: VetReviewIn, request: Request, session: SessionDep, actor: Vet
) -> dict[str, Any]:
    row = await _case(session, case_id)
    try:
        result = await record_vet_review(
            session,
            case=row,
            actor=actor,
            outcome=body.outcome,
            verified_label=body.verified_label,
            notes=body.notes,
            expected_version=body.expected_version,
            request_id=request.state.request_id,
        )
        await session.commit()
        return {"review_id": result.id, "case": _summary(row)}
    except ValueError as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.post("/vet/cases/{case_id}/sample-request")
async def sample_request(
    case_id: UUID, body: SampleRequestIn, request: Request, session: SessionDep, actor: Vet
) -> dict[str, Any]:
    row = await _case(session, case_id)
    try:
        referral = await request_sample(
            session,
            case=row,
            actor=actor,
            sample_identifier=body.sample_identifier,
            expected_version=body.expected_version,
            request_id=request.state.request_id,
        )
        await session.commit()
        return {"referral_id": referral.id, "case": _summary(row)}
    except ValueError as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.post("/vet/cases/{case_id}/lab-referrals/{referral_id}/result")
async def lab_result(
    case_id: UUID,
    referral_id: UUID,
    body: LabResultIn,
    request: Request,
    session: SessionDep,
    actor: Vet,
) -> dict[str, Any]:
    row = await _case(session, case_id)
    referral = await session.get(LabReferral, referral_id)
    if referral is None or referral.health_report_id != row.health_report_id:
        raise HTTPException(status_code=404, detail={"code": "LAB_REFERRAL_NOT_FOUND"})
    try:
        result = await record_lab_result(
            session,
            case=row,
            referral=referral,
            actor=actor,
            result_status=body.result_status,
            result_label=body.result_label,
            expected_version=body.expected_version,
            request_id=request.state.request_id,
        )
        await session.commit()
        return {"lab_result_id": result.id, "case": _summary(row)}
    except ValueError as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.post("/vet/cases/{case_id}/follow-ups")
async def follow_up(
    case_id: UUID, body: FollowUpIn, request: Request, session: SessionDep, actor: Vet
) -> dict[str, Any]:
    row = await _case(session, case_id)
    try:
        saved: CaseFollowUp = await add_follow_up(
            session,
            case=row,
            actor=actor,
            follow_up_type=body.follow_up_type,
            notes=body.notes,
            due_at=body.due_at,
        )
        await session.flush()
        await append_audit(
            session,
            actor_user_id=actor.id,
            action="CASE_FOLLOW_UP_RECORDED",
            resource_type="veterinary_case",
            resource_id=row.id,
            request_id=request.state.request_id,
            details={"follow_up_id": str(saved.id), "type": saved.follow_up_type},
        )
        await session.commit()
        return {"id": saved.id, "status": "RECORDED"}
    except ValueError as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.post("/vet/cases/{case_id}/escalate")
async def escalate(
    case_id: UUID, body: EscalateIn, request: Request, session: SessionDep, actor: Vet
) -> dict[str, Any]:
    row = await _case(session, case_id)
    try:
        from app.operations.cases import ensure_case_access

        ensure_case_access(row, actor)
        row.escalated = True
        row.escalation_level = max(row.escalation_level, body.level)
        await enqueue_alert(
            session,
            deduplication_key=f"case-escalation:{row.id}:{body.level}",
            alert_type="CASE_ESCALATION",
            health_report_id=row.health_report_id,
            context={
                "case_id": str(row.id),
                "level": body.level,
                "reason": body.reason,
                "development_no_send": True,
            },
            escalation_level=body.level,
        )
        await append_audit(
            session,
            actor_user_id=actor.id,
            action="CASE_ESCALATED",
            resource_type="veterinary_case",
            resource_id=row.id,
            request_id=request.state.request_id,
            details={"level": body.level, "reason": body.reason},
        )
        await session.commit()
        return _summary(row)
    except ValueError as exc:
        await session.rollback()
        raise _error(exc) from exc
