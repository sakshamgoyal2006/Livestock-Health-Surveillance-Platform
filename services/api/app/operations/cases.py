from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import append_audit
from app.domain.models import (
    AnalysisArtifact,
    CaseAssignment,
    CaseFollowUp,
    Explanation,
    HealthReport,
    LabReferral,
    LabResult,
    MediaAsset,
    RiskAssessment,
    StatusHistory,
    User,
    VeterinaryCase,
    VetReview,
)
from app.operations.advisories import ensure_advisory
from app.operations.alerts import enqueue_alert
from app.operations.mlops import stage_retraining_candidate
from app.operations.surveillance import CachedWeatherAdapter, nearby_case_context

CASE_TRANSITIONS: dict[str, set[str]] = {
    "TRIAGED": {"ASSIGNED"},
    "ASSIGNED": {"UNDER_REVIEW"},
    "UNDER_REVIEW": {"VET_VERIFIED", "INCONCLUSIVE", "SAMPLE_REQUESTED"},
    "SAMPLE_REQUESTED": {"LAB_PENDING", "INCONCLUSIVE"},
    "LAB_PENDING": {"LAB_CONFIRMED", "LAB_NEGATIVE", "INCONCLUSIVE"},
    "VET_VERIFIED": {"CLOSED", "SAMPLE_REQUESTED"},
    "LAB_CONFIRMED": {"CLOSED"},
    "LAB_NEGATIVE": {"VET_VERIFIED", "INCONCLUSIVE", "CLOSED"},
    "INCONCLUSIVE": {"UNDER_REVIEW", "CLOSED"},
    "CLOSED": set(),
}


def _suspected_label(assessment: RiskAssessment) -> str | None:
    values = (assessment.probabilities or {}).get("suspected_conditions", {})
    if not values:
        return None
    return str(max(values, key=values.get))


async def create_case_from_triage(
    session: AsyncSession,
    *,
    report: HealthReport,
    assessment: RiskAssessment,
    actor_user_id: UUID,
    request_id: str,
) -> VeterinaryCase:
    existing = await session.scalar(
        select(VeterinaryCase).where(VeterinaryCase.health_report_id == report.id)
    )
    if existing is not None:
        return existing
    case = VeterinaryCase(
        health_report_id=report.id,
        original_risk_assessment_id=assessment.id,
        state="TRIAGED",
        suspected_label=_suspected_label(assessment),
        suspected_status="PRELIMINARY_SUSPECTED",
        verified_status="PENDING",
        lab_status="NOT_REQUESTED",
    )
    session.add(case)
    await session.flush()
    previous = report.status
    report.status = "TRIAGED"
    session.add(
        StatusHistory(
            health_report_id=report.id,
            from_status=previous,
            to_status="TRIAGED",
            actor_user_id=actor_user_id,
            reason="Idempotent preliminary triage created veterinarian case",
        )
    )
    await ensure_advisory(session, report, assessment.urgency_tier)
    if assessment.urgency_tier == "EMERGENCY":
        await enqueue_alert(
            session,
            deduplication_key=f"emergency-report:{report.id}",
            alert_type="PRELIMINARY_EMERGENCY_REVIEW",
            health_report_id=report.id,
            recipient_reference="role:VETERINARIAN",
            context={
                "case_id": str(case.id),
                "report_id": str(report.id),
                "urgency": "EMERGENCY",
                "notice": "Preliminary triage only; veterinary review required",
            },
        )
    await append_audit(
        session,
        actor_user_id=actor_user_id,
        action="VETERINARY_CASE_CREATED",
        resource_type="veterinary_case",
        resource_id=case.id,
        request_id=request_id,
        details={"original_risk_assessment_id": str(assessment.id), "state": case.state},
    )
    return case


def ensure_case_access(case: VeterinaryCase, actor: User) -> None:
    if actor.role not in {"VETERINARIAN", "ADMIN"}:
        raise ValueError("CASE_ACCESS_FORBIDDEN")
    if (
        actor.role == "VETERINARIAN"
        and case.assigned_veterinarian_user_id is not None
        and case.assigned_veterinarian_user_id != actor.id
    ):
        raise ValueError("CASE_ASSIGNED_TO_ANOTHER_VETERINARIAN")


async def transition_case(
    session: AsyncSession,
    *,
    case: VeterinaryCase,
    actor: User,
    to_state: str,
    reason: str,
    request_id: str,
    expected_version: int,
) -> VeterinaryCase:
    ensure_case_access(case, actor)
    if case.version != expected_version:
        raise ValueError("STALE_CASE_VERSION")
    if to_state not in CASE_TRANSITIONS.get(case.state, set()):
        raise ValueError("INVALID_CASE_TRANSITION")
    previous = case.state
    case.state = to_state
    case.version += 1
    report = await session.get(HealthReport, case.health_report_id)
    if report is None:
        raise ValueError("REPORT_NOT_FOUND")
    report.status = to_state
    session.add(
        StatusHistory(
            health_report_id=report.id,
            from_status=previous,
            to_status=to_state,
            actor_user_id=actor.id,
            reason=reason,
        )
    )
    await append_audit(
        session,
        actor_user_id=actor.id,
        action="CASE_STATE_TRANSITION",
        resource_type="veterinary_case",
        resource_id=case.id,
        request_id=request_id,
        details={"from": previous, "to": to_state, "reason": reason},
    )
    return case


async def assign_case(
    session: AsyncSession,
    *,
    case: VeterinaryCase,
    actor: User,
    veterinarian: User,
    expected_version: int,
    request_id: str,
) -> VeterinaryCase:
    if actor.role not in {"VETERINARIAN", "ADMIN"}:
        raise ValueError("CASE_ACCESS_FORBIDDEN")
    if veterinarian.role != "VETERINARIAN" or not veterinarian.active:
        raise ValueError("INVALID_VETERINARIAN")
    if actor.role == "VETERINARIAN" and veterinarian.id != actor.id:
        raise ValueError("VETERINARIAN_SELF_ASSIGNMENT_ONLY")
    case.assigned_veterinarian_user_id = veterinarian.id
    session.add(
        CaseAssignment(
            health_report_id=case.health_report_id,
            veterinarian_user_id=veterinarian.id,
            assigned_by_user_id=actor.id,
            active=True,
        )
    )
    return await transition_case(
        session,
        case=case,
        actor=actor,
        to_state="ASSIGNED",
        reason="Case assigned for veterinary review",
        request_id=request_id,
        expected_version=expected_version,
    )


async def record_vet_review(
    session: AsyncSession,
    *,
    case: VeterinaryCase,
    actor: User,
    outcome: str,
    verified_label: str | None,
    notes: str | None,
    expected_version: int,
    request_id: str,
) -> VetReview:
    ensure_case_access(case, actor)
    if actor.role != "VETERINARIAN":
        raise ValueError("VETERINARIAN_VERIFICATION_REQUIRED")
    state = {
        "CONFIRMED": "VET_VERIFIED",
        "CORRECTED": "VET_VERIFIED",
        "INCONCLUSIVE": "INCONCLUSIVE",
    }.get(outcome)
    if state is None or (outcome != "INCONCLUSIVE" and not verified_label):
        raise ValueError("INVALID_REVIEW_OUTCOME")
    review = VetReview(
        health_report_id=case.health_report_id,
        veterinarian_user_id=actor.id,
        outcome_status=outcome,
        verified_label=verified_label,
        notes=notes,
    )
    session.add(review)
    await session.flush()
    await transition_case(
        session,
        case=case,
        actor=actor,
        to_state=state,
        reason=f"Veterinarian review: {outcome}",
        request_id=request_id,
        expected_version=expected_version,
    )
    case.verified_status = "INCONCLUSIVE" if outcome == "INCONCLUSIVE" else "VET_VERIFIED"
    case.verified_label = verified_label
    if outcome != "INCONCLUSIVE" and verified_label:
        await stage_retraining_candidate(
            session,
            report_id=case.health_report_id,
            source="VET_VERIFIED",
            source_record_id=review.id,
            verified_label=verified_label,
            verifier_user_id=actor.id,
        )
    return review


async def request_sample(
    session: AsyncSession,
    *,
    case: VeterinaryCase,
    actor: User,
    sample_identifier: str,
    expected_version: int,
    request_id: str,
) -> LabReferral:
    referral = LabReferral(
        health_report_id=case.health_report_id,
        requested_by_user_id=actor.id,
        sample_identifier=sample_identifier,
        status="REQUESTED",
    )
    session.add(referral)
    await transition_case(
        session,
        case=case,
        actor=actor,
        to_state="SAMPLE_REQUESTED",
        reason=f"Lab sample requested: {sample_identifier}",
        request_id=request_id,
        expected_version=expected_version,
    )
    case.lab_status = "REQUESTED"
    return referral


async def record_lab_result(
    session: AsyncSession,
    *,
    case: VeterinaryCase,
    referral: LabReferral,
    actor: User,
    result_status: str,
    result_label: str,
    expected_version: int,
    request_id: str,
) -> LabResult:
    ensure_case_access(case, actor)
    if result_status not in {"CONFIRMED", "NEGATIVE", "INCONCLUSIVE"}:
        raise ValueError("INVALID_LAB_RESULT")
    if case.state == "SAMPLE_REQUESTED":
        await transition_case(
            session,
            case=case,
            actor=actor,
            to_state="LAB_PENDING",
            reason="Sample received by development lab workflow",
            request_id=request_id,
            expected_version=expected_version,
        )
        expected_version = case.version
    target = {
        "CONFIRMED": "LAB_CONFIRMED",
        "NEGATIVE": "LAB_NEGATIVE",
        "INCONCLUSIVE": "INCONCLUSIVE",
    }[result_status]
    result = LabResult(
        lab_referral_id=referral.id,
        result_label=result_label,
        result_status=result_status,
        recorded_by_user_id=actor.id,
    )
    session.add(result)
    await session.flush()
    await transition_case(
        session,
        case=case,
        actor=actor,
        to_state=target,
        reason=f"Authorized lab result: {result_status}",
        request_id=request_id,
        expected_version=expected_version,
    )
    referral.status = "RESULT_RECORDED"
    case.lab_status = result_status
    if result_status == "CONFIRMED":
        case.verified_status = "LAB_CONFIRMED"
        case.verified_label = result_label
        await stage_retraining_candidate(
            session,
            report_id=case.health_report_id,
            source="LAB_CONFIRMED",
            source_record_id=result.id,
            verified_label=result_label,
            verifier_user_id=actor.id,
        )
    return result


async def case_evidence(session: AsyncSession, case: VeterinaryCase) -> dict[str, Any]:
    report = await session.get(HealthReport, case.health_report_id)
    assessment = await session.get(RiskAssessment, case.original_risk_assessment_id)
    if report is None or assessment is None:
        raise ValueError("CASE_EVIDENCE_INCOMPLETE")
    artifacts = (
        await session.scalars(
            select(AnalysisArtifact).where(AnalysisArtifact.health_report_id == report.id)
        )
    ).all()
    media = (
        await session.scalars(select(MediaAsset).where(MediaAsset.health_report_id == report.id))
    ).all()
    explanations = (
        await session.scalars(
            select(Explanation).where(Explanation.risk_assessment_id == assessment.id)
        )
    ).all()
    reviews = (
        await session.scalars(select(VetReview).where(VetReview.health_report_id == report.id))
    ).all()
    referrals = (
        await session.scalars(select(LabReferral).where(LabReferral.health_report_id == report.id))
    ).all()
    results: list[LabResult] = []
    if referrals:
        results = list(
            (
                await session.scalars(
                    select(LabResult).where(
                        LabResult.lab_referral_id.in_([row.id for row in referrals])
                    )
                )
            ).all()
        )
    history = (
        await session.scalars(
            select(StatusHistory)
            .where(StatusHistory.health_report_id == report.id)
            .order_by(StatusHistory.created_at)
        )
    ).all()
    followups = (
        await session.scalars(
            select(CaseFollowUp).where(CaseFollowUp.veterinary_case_id == case.id)
        )
    ).all()
    return {
        "case": {column.name: getattr(case, column.name) for column in case.__table__.columns},
        "raw_observations": {
            column.name: getattr(report, column.name)
            for column in report.__table__.columns
            if column.name != "location"
        },
        "original_prediction": {
            "id": assessment.id,
            "immutable": True,
            "model_version": assessment.model_version,
            "rule_version": assessment.rule_version,
            "feature_schema_version": assessment.feature_schema_version,
            "urgency_tier": assessment.urgency_tier,
            "probabilities": assessment.probabilities,
            "decision_trace": assessment.decision_trace,
            "preliminary": assessment.preliminary,
        },
        "analysis_artifacts": [
            {
                "type": row.artifact_type,
                "status": row.status,
                "adapter_version": row.adapter_version,
                "payload": row.payload,
            }
            for row in artifacts
        ],
        "media": [
            {
                "id": row.id,
                "mime_type": row.mime_type,
                "byte_size": row.byte_size,
                "checksum": row.checksum_sha256,
                "status": row.upload_status,
            }
            for row in media
        ],
        "explanations": [row.content for row in explanations],
        "nearby_context": await nearby_case_context(session, report),
        "weather": await CachedWeatherAdapter().nearby(
            session, latitude=report.latitude, longitude=report.longitude
        ),
        "reviews": [
            {
                "id": row.id,
                "outcome": row.outcome_status,
                "label": row.verified_label,
                "notes": row.notes,
            }
            for row in reviews
        ],
        "lab_referrals": [
            {"id": row.id, "sample_identifier": row.sample_identifier, "status": row.status}
            for row in referrals
        ],
        "lab_results": [
            {"id": row.id, "label": row.result_label, "status": row.result_status}
            for row in results
        ],
        "follow_ups": [
            {"id": row.id, "type": row.follow_up_type, "notes": row.notes, "due_at": row.due_at}
            for row in followups
        ],
        "timeline": [
            {
                "from": row.from_status,
                "to": row.to_status,
                "reason": row.reason,
                "at": row.created_at,
            }
            for row in history
        ],
        "clinical_notice": (
            "Decision support only; this is not a confirmed diagnosis until an "
            "authorized outcome is recorded."
        ),
    }


async def add_follow_up(
    session: AsyncSession,
    *,
    case: VeterinaryCase,
    actor: User,
    follow_up_type: str,
    notes: str,
    due_at: datetime | None,
) -> CaseFollowUp:
    ensure_case_access(case, actor)
    row = CaseFollowUp(
        veterinary_case_id=case.id,
        recorded_by_user_id=actor.id,
        follow_up_type=follow_up_type,
        notes=notes,
        due_at=due_at,
    )
    session.add(row)
    return row
