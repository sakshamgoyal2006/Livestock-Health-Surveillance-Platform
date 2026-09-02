from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    DatasetVersion,
    HealthReport,
    ModelVersion,
    PromotionApproval,
    RetrainingCandidate,
    User,
)

LABELS = ["LOW", "VET_REVIEW", "EMERGENCY"]
CURRENT_MODEL_NAME = "interpretable-risk-demo-1.0.0"
FEATURE_SCHEMA_VERSION = "triage-features-v1.0.0"
EVALUATOR_VERSION = "locked-demo-evaluator-1.0.0"


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


@lru_cache
def locked_benchmark() -> dict[str, Any]:
    path = Path(__file__).with_name("config") / "locked_benchmark.v1.json"
    return cast(dict[str, Any], json.loads(path.read_text("utf-8")))


async def stage_retraining_candidate(
    session: AsyncSession,
    *,
    report_id: UUID,
    source: Literal["VET_VERIFIED", "LAB_CONFIRMED"],
    source_record_id: UUID,
    verified_label: str,
    verifier_user_id: UUID,
) -> RetrainingCandidate:
    if source not in {"VET_VERIFIED", "LAB_CONFIRMED"}:
        raise ValueError("PSEUDO_LABEL_REJECTED")
    report = await session.get(HealthReport, report_id)
    verifier = await session.get(User, verifier_user_id)
    if report is None or verifier is None or verifier.role not in {"VETERINARIAN", "ADMIN"}:
        raise ValueError("UNAUTHORIZED_VERIFICATION_PROVENANCE")
    reporter = await session.get(User, report.reporter_user_id)
    payload = {
        "report_id": str(report_id),
        "source": source,
        "source_record_id": str(source_record_id),
        "verified_label": verified_label,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
    }
    deduplication_hash = _canonical_hash(payload)
    existing = await session.scalar(
        select(RetrainingCandidate).where(RetrainingCandidate.health_report_id == report_id)
    )
    if existing is not None:
        if existing.deduplication_hash != deduplication_hash:
            existing.status = "CONFLICT_REVIEW_REQUIRED"
            existing.quality_review_status = "CONFLICT"
        return existing
    candidate = RetrainingCandidate(
        health_report_id=report_id,
        verification_source=source,
        verified_label=verified_label,
        status="STAGED",
        source_record_id=source_record_id,
        provenance={
            **payload,
            "verifier_user_id": str(verifier_user_id),
            "reporter_is_synthetic": bool(reporter and reporter.synthetic),
            "prediction_used_as_label": False,
        },
        quality_review_status="PENDING",
        deduplication_hash=deduplication_hash,
        immutable_checksum=_canonical_hash({**payload, "raw_report_version": report.version}),
    )
    session.add(candidate)
    return candidate


async def build_dataset_version(
    session: AsyncSession,
    *,
    name: str,
    allow_small_synthetic_demo: bool,
) -> DatasetVersion:
    existing = await session.scalar(select(DatasetVersion).where(DatasetVersion.name == name))
    if existing is not None:
        return existing
    candidates = (
        await session.scalars(
            select(RetrainingCandidate)
            .where(
                RetrainingCandidate.status == "READY",
                RetrainingCandidate.quality_review_status == "APPROVED",
                RetrainingCandidate.dataset_version_id.is_(None),
            )
            .order_by(RetrainingCandidate.created_at, RetrainingCandidate.id)
        )
    ).all()
    minimum = 1 if allow_small_synthetic_demo else 10
    if len(candidates) < minimum:
        raise ValueError("INSUFFICIENT_VERIFIED_BATCH")
    if allow_small_synthetic_demo and not all(
        bool(candidate.provenance.get("reporter_is_synthetic")) for candidate in candidates
    ):
        raise ValueError("SMALL_BATCH_ONLY_ALLOWED_FOR_SYNTHETIC_DEMO")
    manifest = [
        {
            "candidate_id": str(candidate.id),
            "report_id": str(candidate.health_report_id),
            "label": candidate.verified_label,
            "source": candidate.verification_source,
            "checksum": candidate.immutable_checksum,
        }
        for candidate in candidates
    ]
    benchmark = locked_benchmark()
    dataset = DatasetVersion(
        name=name,
        checksum=_canonical_hash(manifest),
        provenance={
            "manifest": manifest,
            "verification_sources": sorted({item["source"] for item in manifest}),
            "prediction_labels_included": False,
            "split_policy": "group-aware and temporal; locked benchmark excluded from training",
            "code_version": EVALUATOR_VERSION,
        },
        immutable=True,
        status="LOCKED",
        row_count=len(manifest),
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        locked_benchmark_checksum=_canonical_hash(benchmark),
    )
    session.add(dataset)
    await session.flush()
    for candidate in candidates:
        candidate.dataset_version_id = dataset.id
        candidate.status = "IN_DATASET"
    return dataset


def _baseline_probabilities(row: dict[str, Any]) -> dict[str, float]:
    low = 0.4
    review = 0.8 * int(row["severity_score"] == 1)
    review += 0.45 * int(row["appetite_loss"])
    review += 0.2 * int(row["vaccination_unknown"])
    review += 0.65 * int(row["missing_count"] >= 4)
    emergency = -1.0 + 1.15 * int(row["severity_score"] == 2)
    emergency += 0.9 * int(row["respiration_flag"])
    emergency += 1.1 * int(row["mobility_flag"])
    emergency += 0.9 * int(row["mortality_count"] > 0)
    scores = [low, review, emergency]
    values = [math.exp(score - max(scores)) for score in scores]
    total = sum(values)
    return dict(zip(LABELS, (value / total for value in values), strict=True))


def _evaluate(
    mode: Literal["BASELINE_EQUIVALENT", "INTENTIONAL_REGRESSION_FIXTURE"],
) -> dict[str, Any]:
    benchmark = locked_benchmark()
    rows = cast(list[dict[str, Any]], benchmark["rows"])
    predictions = []
    brier = 0.0
    for row in rows:
        probabilities = (
            _baseline_probabilities(row)
            if mode == "BASELINE_EQUIVALENT"
            else {"LOW": 0.98, "VET_REVIEW": 0.01, "EMERGENCY": 0.01}
        )
        predicted = max(LABELS, key=lambda label: probabilities[label])
        predictions.append((row["label"], predicted))
        brier += sum((probabilities[label] - int(row["label"] == label)) ** 2 for label in LABELS)
    emergency_total = sum(truth == "EMERGENCY" for truth, _ in predictions)
    emergency_true = sum(
        truth == "EMERGENCY" and predicted == "EMERGENCY" for truth, predicted in predictions
    )
    return {
        "benchmark_version": benchmark["version"],
        "benchmark_provenance": benchmark["provenance"],
        "rows": len(rows),
        "group_count": len({row["group"] for row in rows}),
        "emergency_sensitivity": emergency_true / emergency_total,
        "multiclass_brier_score": round(brier / len(rows), 6),
        "correct": sum(truth == predicted for truth, predicted in predictions),
        "class_counts": dict(Counter(row["label"] for row in rows)),
        "calibration_status": "DEMO_UNVALIDATED",
        "warning": "Synthetic locked-benchmark metrics only; not clinical performance",
    }


async def evaluate_candidate(
    session: AsyncSession,
    *,
    dataset: DatasetVersion,
    name: str,
    mode: Literal["BASELINE_EQUIVALENT", "INTENTIONAL_REGRESSION_FIXTURE"],
) -> ModelVersion:
    if not dataset.immutable or dataset.status != "LOCKED":
        raise ValueError("DATASET_NOT_LOCKED")
    existing = await session.scalar(select(ModelVersion).where(ModelVersion.name == name))
    if existing is not None:
        return existing
    current = await session.scalar(
        select(ModelVersion).where(ModelVersion.status == "ACTIVE", ModelVersion.modality == "RISK")
    )
    current_metrics = (
        cast(dict[str, Any], current.metadata_json.get("locked_benchmark_metrics", {}))
        if current
        else {"emergency_sensitivity": 0.5, "multiclass_brier_score": 0.462228}
    )
    metrics = _evaluate(mode)
    regression_reasons = []
    if metrics["emergency_sensitivity"] < float(current_metrics["emergency_sensitivity"]):
        regression_reasons.append("EMERGENCY_SENSITIVITY_REGRESSION")
    if metrics["multiclass_brier_score"] > float(current_metrics["multiclass_brier_score"]) + 0.02:
        regression_reasons.append("CALIBRATION_BRIER_REGRESSION")
    metadata = {
        "dataset_version_id": str(dataset.id),
        "dataset_checksum": dataset.checksum,
        "locked_benchmark_checksum": dataset.locked_benchmark_checksum,
        "locked_benchmark_metrics": metrics,
        "comparison_to_model": current.name if current else None,
        "comparison_result": "REJECTED_REGRESSION" if regression_reasons else "PASS_NO_REGRESSION",
        "regression_reasons": regression_reasons,
        "threshold_version": "thresholds-demo-1.0.0",
        "code_version": EVALUATOR_VERSION,
        "artifact_storage": "LOCAL_DATABASE_METADATA_DEMO",
        "auto_promoted": False,
    }
    metadata["artifact_checksum"] = _canonical_hash(metadata)
    model = ModelVersion(
        name=name,
        modality="RISK",
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        status="REJECTED_REGRESSION" if regression_reasons else "CANDIDATE_EVALUATED",
        metadata_json=metadata,
    )
    session.add(model)
    return model


async def promote_model(session: AsyncSession, model: ModelVersion) -> ModelVersion:
    approval = await session.scalar(
        select(PromotionApproval)
        .where(
            PromotionApproval.model_version_id == model.id,
            PromotionApproval.decision == "APPROVED",
        )
        .order_by(PromotionApproval.created_at.desc())
    )
    if approval is None:
        raise ValueError("MANUAL_APPROVAL_REQUIRED")
    if model.status == "REJECTED_REGRESSION":
        raise ValueError("REGRESSING_MODEL_CANNOT_BE_PROMOTED")
    current = await session.scalar(
        select(ModelVersion).where(ModelVersion.status == "ACTIVE", ModelVersion.modality == "RISK")
    )
    metadata = dict(model.metadata_json)
    metadata["previous_model_id"] = str(current.id) if current else None
    metadata["promotion_approval_id"] = str(approval.id)
    model.metadata_json = metadata
    if current is not None and current.id != model.id:
        current.status = "ROLLBACK_AVAILABLE"
    model.status = "ACTIVE"
    return model


async def rollback_model(session: AsyncSession, model: ModelVersion) -> ModelVersion:
    previous_id = model.metadata_json.get("previous_model_id")
    if model.status != "ACTIVE" or not previous_id:
        raise ValueError("ROLLBACK_TARGET_UNAVAILABLE")
    previous = await session.get(ModelVersion, UUID(str(previous_id)))
    if previous is None:
        raise ValueError("ROLLBACK_TARGET_UNAVAILABLE")
    model.status = "ROLLED_BACK"
    previous.status = "ACTIVE"
    return previous
