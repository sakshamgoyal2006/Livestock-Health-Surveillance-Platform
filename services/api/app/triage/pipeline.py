from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import append_audit
from app.domain.models import (
    AnalysisArtifact,
    DiseaseHistory,
    Explanation,
    FeatureSnapshot,
    HealthReport,
    MediaAsset,
    MediaBlob,
    RiskAssessment,
    TriageJob,
    VaccinationRecord,
    WeatherSnapshot,
)
from app.triage.contracts import TriageDecision, TriageJobResult, VisionPrediction
from app.triage.features import ContextFeatures, build_features
from app.triage.nlp import DeterministicNLPAdapter, TranscriptEntrySpeechAdapter
from app.triage.risk import PIPELINE_VERSION, score_interpretable_baseline
from app.triage.rules import evaluate_rules
from app.triage.vision import DeterministicVisionAdapter, ImageRejected


def _hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _report_value(report: Any, field: str) -> Any:
    return report.get(field) if isinstance(report, dict) else getattr(report, field)


def report_input_fingerprint(report: Any, media: list[tuple[UUID, str]] | None = None) -> str:
    return _hash(
        {
            "report": {
                "id": _report_value(report, "id"),
                "severity": _report_value(report, "severity"),
                "appetite": _report_value(report, "appetite"),
                "water_intake": _report_value(report, "water_intake"),
                "mobility": _report_value(report, "mobility"),
                "respiration": _report_value(report, "respiration"),
                "temperature_c": _report_value(report, "temperature_c"),
                "mortality_count": _report_value(report, "mortality_count"),
                "notes": _report_value(report, "notes"),
                "voice_transcript": _report_value(report, "voice_transcript"),
            },
            "media": media or [],
            "pipeline": PIPELINE_VERSION,
        }
    )


def initial_job_values(report: Any) -> dict[str, Any]:
    report_id = UUID(str(_report_value(report, "id")))
    fingerprint = report_input_fingerprint(report)
    return {
        "health_report_id": report_id,
        "job_key": f"{report_id}:{PIPELINE_VERSION}:{fingerprint}",
        "input_fingerprint": fingerprint,
        "pipeline_version": PIPELINE_VERSION,
        "status": "PENDING",
        "attempt_count": 0,
        "max_attempts": 3,
    }


async def _current_fingerprint(session: AsyncSession, report: HealthReport) -> str:
    media = (
        await session.scalars(
            select(MediaAsset)
            .where(
                MediaAsset.health_report_id == report.id,
                MediaAsset.upload_status == "COMPLETE",
            )
            .order_by(MediaAsset.id)
        )
    ).all()
    return report_input_fingerprint(report, [(asset.id, asset.checksum_sha256) for asset in media])


async def enqueue_current_triage(
    session: AsyncSession, report_id: UUID, *, force_retry: bool = False
) -> TriageJob:
    report = await session.get(HealthReport, report_id)
    if report is None:
        raise ValueError("REPORT_NOT_FOUND")
    fingerprint = await _current_fingerprint(session, report)
    key = f"{report.id}:{PIPELINE_VERSION}:{fingerprint}"
    existing = await session.scalar(select(TriageJob).where(TriageJob.job_key == key))
    if existing is not None:
        if (
            force_retry
            and existing.status == "FAILED"
            and existing.attempt_count < existing.max_attempts
        ):
            existing.status = "PENDING"
            existing.last_error_code = None
            await session.commit()
        return existing
    job = TriageJob(
        health_report_id=report.id,
        job_key=key,
        input_fingerprint=fingerprint,
        pipeline_version=PIPELINE_VERSION,
        status="PENDING",
        attempt_count=0,
        max_attempts=3,
    )
    session.add(job)
    await session.commit()
    return job


async def _context(session: AsyncSession, report: HealthReport) -> ContextFeatures:
    prior_count: int | None = None
    vaccination_count: int | None = None
    if report.animal_id is not None:
        prior_count = int(
            await session.scalar(
                select(func.count())
                .select_from(DiseaseHistory)
                .where(DiseaseHistory.animal_id == report.animal_id)
            )
            or 0
        )
        vaccination_count = int(
            await session.scalar(
                select(func.count())
                .select_from(VaccinationRecord)
                .where(VaccinationRecord.animal_id == report.animal_id)
            )
            or 0
        )
    weather_temperature: float | None = None
    weather_humidity: float | None = None
    nearby: int | None = None
    if report.location is not None:
        weather = await session.scalar(
            select(WeatherSnapshot)
            .where(
                WeatherSnapshot.observed_at <= report.received_at_server,
                func.ST_DWithin(WeatherSnapshot.location, report.location, 50_000),
            )
            .order_by(
                func.ST_Distance(WeatherSnapshot.location, report.location),
                WeatherSnapshot.observed_at.desc(),
            )
            .limit(1)
        )
        if weather is not None:
            raw_temperature = weather.payload.get("temperature_c")
            raw_humidity = weather.payload.get("humidity_pct")
            weather_temperature = (
                float(raw_temperature) if isinstance(raw_temperature, (int, float)) else None
            )
            weather_humidity = (
                float(raw_humidity) if isinstance(raw_humidity, (int, float)) else None
            )
        nearby = int(
            await session.scalar(
                select(func.count())
                .select_from(HealthReport)
                .where(
                    HealthReport.id != report.id,
                    HealthReport.received_at_server >= datetime.now(UTC) - timedelta(days=7),
                    func.ST_DWithin(HealthReport.location, report.location, 10_000),
                )
            )
            or 0
        )
    return ContextFeatures(
        prior_condition_count=prior_count,
        vaccination_record_count=vaccination_count,
        weather_temperature_c=weather_temperature,
        weather_humidity_pct=weather_humidity,
        nearby_recent_suspected_count=nearby,
    )


async def _nlp_artifact(session: AsyncSession, report: HealthReport) -> tuple[Any | None, str]:
    speech = TranscriptEntrySpeechAdapter()
    transcript = speech.transcribe(None, transcript=report.voice_transcript)
    combined = " ".join(value for value in (report.notes, transcript) if value).strip()
    if not combined:
        return None, "NOT_PROVIDED"
    source: Literal["FREE_TEXT", "VOICE_TRANSCRIPT", "PROVIDER"] = (
        "VOICE_TRANSCRIPT" if transcript and not report.notes else "FREE_TEXT"
    )
    extraction = DeterministicNLPAdapter().extract(
        combined, language_hint=report.language, source=source
    )
    fingerprint = _hash({"text": combined, "version": extraction.adapter_version})
    existing = await session.scalar(
        select(AnalysisArtifact).where(
            AnalysisArtifact.health_report_id == report.id,
            AnalysisArtifact.artifact_type == "NLP",
            AnalysisArtifact.input_fingerprint == fingerprint,
        )
    )
    if existing is None:
        session.add(
            AnalysisArtifact(
                health_report_id=report.id,
                media_asset_id=None,
                artifact_type="NLP",
                input_fingerprint=fingerprint,
                adapter_version=extraction.adapter_version,
                status="COMPLETED",
                payload=extraction.model_dump(mode="json"),
            )
        )
    return extraction, "AVAILABLE"


async def _vision_artifact(
    session: AsyncSession, report: HealthReport
) -> tuple[VisionPrediction | None, str]:
    rows = (
        await session.execute(
            select(MediaAsset, MediaBlob)
            .join(MediaBlob, MediaBlob.media_asset_id == MediaAsset.id)
            .where(
                MediaAsset.health_report_id == report.id,
                MediaAsset.upload_status == "COMPLETE",
                MediaAsset.media_type == "IMAGE",
            )
            .order_by(MediaAsset.created_at.desc())
        )
    ).all()
    if not rows:
        return None, "NOT_PROVIDED"
    adapter = DeterministicVisionAdapter()
    accepted: list[VisionPrediction] = []
    rejected = False
    for asset, blob in rows:
        fingerprint = _hash(
            {"asset": asset.id, "checksum": asset.checksum_sha256, "version": adapter.version}
        )
        existing = await session.scalar(
            select(AnalysisArtifact).where(
                AnalysisArtifact.health_report_id == report.id,
                AnalysisArtifact.artifact_type == "VISION",
                AnalysisArtifact.input_fingerprint == fingerprint,
            )
        )
        if existing is not None:
            if existing.status == "COMPLETED":
                accepted.append(VisionPrediction.model_validate(existing.payload))
            else:
                rejected = True
            continue
        try:
            prediction = adapter.predict(blob.content)
            accepted.append(prediction)
            status = "COMPLETED"
            payload = prediction.model_dump(mode="json")
        except ImageRejected as exc:
            rejected = True
            status = "REJECTED"
            payload = {"code": exc.code, "message": str(exc)}
        session.add(
            AnalysisArtifact(
                health_report_id=report.id,
                media_asset_id=asset.id,
                artifact_type="VISION",
                input_fingerprint=fingerprint,
                adapter_version=adapter.version,
                status=status,
                payload=payload,
            )
        )
    if accepted:
        return max(accepted, key=lambda item: item.quality.score), "AVAILABLE"
    return None, "QUALITY_REJECTED" if rejected else "MODEL_UNAVAILABLE"


async def run_triage_job(
    session: AsyncSession,
    job: TriageJob,
    *,
    request_id: str,
    actor_user_id: UUID | None,
) -> TriageJobResult:
    if job.status == "COMPLETED" and job.risk_assessment_id is not None:
        assessment = await session.get(RiskAssessment, job.risk_assessment_id)
        if assessment is not None:
            decision = TriageDecision.model_validate(assessment.decision_trace["decision"])
            return TriageJobResult(
                job_id=job.id,
                status="COMPLETED",
                attempt_count=job.attempt_count,
                decision=decision,
            )
    if job.attempt_count >= job.max_attempts:
        return TriageJobResult(
            job_id=job.id,
            status="FAILED",
            attempt_count=job.attempt_count,
            error_code=job.last_error_code or "MAX_ATTEMPTS_EXCEEDED",
        )
    job.status = "RUNNING"
    job.attempt_count += 1
    await session.commit()
    try:
        report = await session.get(HealthReport, job.health_report_id)
        if report is None:
            raise ValueError("REPORT_NOT_FOUND")
        nlp, nlp_status = await _nlp_artifact(session, report)
        vision, vision_status = await _vision_artifact(session, report)
        context = await _context(session, report)
        features = build_features(report, nlp=nlp, vision=vision, context=context)
        rules = evaluate_rules(
            {
                "severity": report.severity,
                "appetite": report.appetite,
                "water_intake": report.water_intake,
                "mobility": report.mobility,
                "respiration": report.respiration,
                "temperature_c": report.temperature_c,
                "mortality_count": report.mortality_count,
            }
        )
        decision = score_interpretable_baseline(report.id, features, rules)
        decision.modality_status["nlp"] = nlp_status
        decision.modality_status["vision"] = vision_status
        snapshot = FeatureSnapshot(
            health_report_id=report.id,
            feature_schema_version=features.feature_schema_version,
            features=features.model_dump(mode="json"),
        )
        session.add(snapshot)
        assessment = RiskAssessment(
            health_report_id=report.id,
            model_version=decision.model_version,
            rule_version=decision.rule_version,
            feature_schema_version=decision.feature_schema_version,
            urgency_tier=decision.urgency_tier,
            probabilities={
                "urgency": decision.urgency_probabilities,
                "suspected_conditions": decision.suspected_condition_likelihoods,
                "uncertainty": decision.uncertainty,
                "calibration_status": decision.calibration_status,
            },
            decision_trace={"decision": decision.model_dump(mode="json")},
            preliminary=True,
        )
        session.add(assessment)
        await session.flush()
        decision.assessment_id = assessment.id
        assessment.decision_trace = {"decision": decision.model_dump(mode="json")}
        session.add(
            Explanation(
                risk_assessment_id=assessment.id,
                explanation_type="FEATURE_CONTRIBUTIONS",
                content={
                    "label": "Feature contributions, not causal percentage changes",
                    "items": [item.model_dump(mode="json") for item in decision.contributions],
                },
            )
        )
        job.status = "COMPLETED"
        job.last_error_code = None
        job.risk_assessment_id = assessment.id
        await append_audit(
            session,
            actor_user_id=actor_user_id,
            action="TRIAGE_COMPLETED",
            resource_type="health_report",
            resource_id=report.id,
            request_id=request_id,
            details={
                "job_id": str(job.id),
                "urgency_tier": decision.urgency_tier,
                "rule_version": decision.rule_version,
                "model_version": decision.model_version,
                "feature_schema_version": decision.feature_schema_version,
                "preliminary": True,
            },
        )
        await session.commit()
        return TriageJobResult(
            job_id=job.id,
            status="COMPLETED",
            attempt_count=job.attempt_count,
            decision=decision,
        )
    except Exception as exc:
        await session.rollback()
        failed = await session.get(TriageJob, job.id)
        if failed is None:
            raise
        failed.status = "FAILED"
        failed.last_error_code = getattr(exc, "code", type(exc).__name__.upper())[:80]
        await session.commit()
        return TriageJobResult(
            job_id=failed.id,
            status="FAILED",
            attempt_count=failed.attempt_count,
            error_code=failed.last_error_code,
        )


async def run_report_triage(
    session: AsyncSession,
    report_id: UUID,
    *,
    request_id: str,
    actor_user_id: UUID | None,
    force_retry: bool = False,
) -> TriageJobResult:
    job = await enqueue_current_triage(session, report_id, force_retry=force_retry)
    return await run_triage_job(session, job, request_id=request_id, actor_user_id=actor_user_id)


async def latest_decision(session: AsyncSession, report_id: UUID) -> TriageDecision | None:
    assessment = await session.scalar(
        select(RiskAssessment)
        .where(RiskAssessment.health_report_id == report_id)
        .order_by(RiskAssessment.created_at.desc())
        .limit(1)
    )
    if assessment is None:
        return None
    return TriageDecision.model_validate(assessment.decision_trace["decision"])
