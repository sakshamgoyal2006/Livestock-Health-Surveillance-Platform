from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from app.api.deps import SessionDep, require_roles
from app.core.audit import append_audit
from app.domain.models import (
    DatasetVersion,
    ModelVersion,
    PromotionApproval,
    RetrainingCandidate,
    User,
)
from app.operations.mlops import (
    build_dataset_version,
    evaluate_candidate,
    promote_model,
    rollback_model,
)
from app.schemas.checkpoint3 import (
    CandidateEvaluationIn,
    CandidateReviewIn,
    DatasetBuildIn,
    PromotionApprovalIn,
)

router = APIRouter(prefix="/api/v1/mlops", tags=["verified active learning"])
Admin = Annotated[User, Depends(require_roles("ADMIN"))]


def _error(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=409, detail={"code": str(exc), "message": str(exc).replace("_", " ").title()}
    )


@router.get("/overview")
async def overview(session: SessionDep, actor: Admin) -> dict[str, Any]:
    del actor
    candidates = (await session.scalars(select(RetrainingCandidate))).all()
    datasets = (await session.scalars(select(DatasetVersion))).all()
    models = (
        await session.scalars(select(ModelVersion).order_by(ModelVersion.created_at.desc()))
    ).all()
    return {
        "candidates": [
            {
                "id": row.id,
                "source": row.verification_source,
                "status": row.status,
                "quality_review_status": row.quality_review_status,
                "prediction_used_as_label": row.provenance.get("prediction_used_as_label"),
            }
            for row in candidates
        ],
        "datasets": [
            {
                "id": row.id,
                "name": row.name,
                "checksum": row.checksum,
                "immutable": row.immutable,
                "rows": row.row_count,
            }
            for row in datasets
        ],
        "models": [
            {"id": row.id, "name": row.name, "status": row.status, "metadata": row.metadata_json}
            for row in models
        ],
        "controls": {
            "auto_deploy": False,
            "prediction_labels_allowed": False,
            "manual_approval_required": True,
        },
    }


@router.post("/candidates/{candidate_id}/review")
async def review_candidate(
    candidate_id: UUID, body: CandidateReviewIn, request: Request, session: SessionDep, actor: Admin
) -> dict[str, Any]:
    row = await session.get(RetrainingCandidate, candidate_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "CANDIDATE_NOT_FOUND"})
    row.quality_review_status = body.decision
    row.status = "READY" if body.decision == "APPROVED" else "REJECTED_QUALITY"
    row.provenance = {
        **row.provenance,
        "quality_reviewer_user_id": str(actor.id),
        "quality_review_note": body.note,
    }
    await append_audit(
        session,
        actor_user_id=actor.id,
        action="RETRAINING_CANDIDATE_REVIEWED",
        resource_type="retraining_candidate",
        resource_id=row.id,
        request_id=request.state.request_id,
        details={"decision": body.decision},
    )
    await session.commit()
    return {"id": row.id, "status": row.status}


@router.post("/datasets")
async def build_dataset(
    body: DatasetBuildIn, request: Request, session: SessionDep, actor: Admin
) -> dict[str, Any]:
    try:
        row = await build_dataset_version(
            session, name=body.name, allow_small_synthetic_demo=body.allow_small_synthetic_demo
        )
        await append_audit(
            session,
            actor_user_id=actor.id,
            action="IMMUTABLE_DATASET_BUILT",
            resource_type="dataset_version",
            resource_id=row.id,
            request_id=request.state.request_id,
            details={"checksum": row.checksum, "rows": row.row_count},
        )
        await session.commit()
        return {
            "id": row.id,
            "name": row.name,
            "checksum": row.checksum,
            "immutable": row.immutable,
            "rows": row.row_count,
        }
    except ValueError as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.post("/models/evaluate")
async def evaluate(
    body: CandidateEvaluationIn, request: Request, session: SessionDep, actor: Admin
) -> dict[str, Any]:
    dataset = await session.get(DatasetVersion, body.dataset_version_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail={"code": "DATASET_NOT_FOUND"})
    try:
        row = await evaluate_candidate(session, dataset=dataset, name=body.name, mode=body.mode)
        await session.flush()
        await append_audit(
            session,
            actor_user_id=actor.id,
            action="MODEL_CANDIDATE_EVALUATED",
            resource_type="model_version",
            resource_id=row.id,
            request_id=request.state.request_id,
            details={"result": row.metadata_json["comparison_result"], "auto_promoted": False},
        )
        await session.commit()
        return {"id": row.id, "name": row.name, "status": row.status, "metadata": row.metadata_json}
    except ValueError as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.post("/models/{model_id}/approval")
async def approve(
    model_id: UUID, body: PromotionApprovalIn, request: Request, session: SessionDep, actor: Admin
) -> dict[str, Any]:
    model = await session.get(ModelVersion, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail={"code": "MODEL_NOT_FOUND"})
    row = PromotionApproval(
        model_version_id=model.id,
        approved_by_user_id=actor.id,
        decision=body.decision,
        rationale=body.rationale,
    )
    session.add(row)
    await session.flush()
    await append_audit(
        session,
        actor_user_id=actor.id,
        action="MODEL_PROMOTION_DECISION_RECORDED",
        resource_type="model_version",
        resource_id=model.id,
        request_id=request.state.request_id,
        details={"decision": body.decision, "approval_id": str(row.id)},
    )
    await session.commit()
    return {"approval_id": row.id, "decision": row.decision}


@router.post("/models/{model_id}/promote")
async def promote(
    model_id: UUID, request: Request, session: SessionDep, actor: Admin
) -> dict[str, Any]:
    model = await session.get(ModelVersion, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail={"code": "MODEL_NOT_FOUND"})
    try:
        row = await promote_model(session, model)
        await append_audit(
            session,
            actor_user_id=actor.id,
            action="MODEL_MANUALLY_PROMOTED",
            resource_type="model_version",
            resource_id=row.id,
            request_id=request.state.request_id,
            details={"approval_required": True},
        )
        await session.commit()
        return {"id": row.id, "status": row.status}
    except ValueError as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.post("/models/{model_id}/rollback")
async def rollback(
    model_id: UUID, request: Request, session: SessionDep, actor: Admin
) -> dict[str, Any]:
    model = await session.get(ModelVersion, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail={"code": "MODEL_NOT_FOUND"})
    try:
        restored = await rollback_model(session, model)
        await append_audit(
            session,
            actor_user_id=actor.id,
            action="MODEL_ROLLED_BACK",
            resource_type="model_version",
            resource_id=restored.id,
            request_id=request.state.request_id,
            details={"rolled_back_model_id": str(model.id)},
        )
        await session.commit()
        return {"restored_model_id": restored.id, "status": restored.status}
    except ValueError as exc:
        await session.rollback()
        raise _error(exc) from exc
