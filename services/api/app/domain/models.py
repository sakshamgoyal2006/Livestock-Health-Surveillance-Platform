from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from geoalchemy2 import Geography
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def uuid_column() -> Mapped[UUID]:
    return mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[UUID] = uuid_column()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class FarmerProfile(Base, TimestampMixin):
    __tablename__ = "farmer_profiles"
    id: Mapped[UUID] = uuid_column()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    preferred_language: Mapped[str] = mapped_column(String(8), default="en")


class FieldWorkerProfile(Base, TimestampMixin):
    __tablename__ = "field_worker_profiles"
    id: Mapped[UUID] = uuid_column()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    service_area: Mapped[str | None] = mapped_column(String(120))


class VeterinarianProfile(Base, TimestampMixin):
    __tablename__ = "veterinarian_profiles"
    id: Mapped[UUID] = uuid_column()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    registration_reference: Mapped[str | None] = mapped_column(String(100))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class AdministrativeArea(Base, TimestampMixin):
    __tablename__ = "administrative_areas"
    id: Mapped[UUID] = uuid_column()
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("administrative_areas.id"))
    boundary: Mapped[Any | None] = mapped_column(Geography("MULTIPOLYGON", srid=4326))


class Farm(Base, TimestampMixin):
    __tablename__ = "farms"
    id: Mapped[UUID] = uuid_column()
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    village_name: Mapped[str] = mapped_column(String(120), nullable=False)
    administrative_area_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("administrative_areas.id")
    )
    location: Mapped[Any | None] = mapped_column(Geography("POINT", srid=4326))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    location_precision: Mapped[str] = mapped_column(String(24), default="VILLAGE_ONLY")
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    __table_args__ = (
        Index("ix_farms_location_gist", "location", postgresql_using="gist"),
        CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="latitude"),
        CheckConstraint("longitude IS NULL OR longitude BETWEEN -180 AND 180", name="longitude"),
    )


class Herd(Base, TimestampMixin):
    __tablename__ = "herds"
    id: Mapped[UUID] = uuid_column()
    farm_id: Mapped[UUID] = mapped_column(ForeignKey("farms.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    species: Mapped[str] = mapped_column(String(20), nullable=False)
    animal_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    __table_args__ = (CheckConstraint("animal_count >= 1", name="animal_count_positive"),)


class Animal(Base, TimestampMixin):
    __tablename__ = "animals"
    id: Mapped[UUID] = uuid_column()
    farm_id: Mapped[UUID] = mapped_column(ForeignKey("farms.id"), index=True)
    herd_id: Mapped[UUID | None] = mapped_column(ForeignKey("herds.id"))
    tag_number: Mapped[str] = mapped_column(String(80), nullable=False)
    species: Mapped[str] = mapped_column(String(20), nullable=False)
    sex: Mapped[str] = mapped_column(String(16), nullable=False)
    age_band: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    __table_args__ = (UniqueConstraint("farm_id", "tag_number"),)


class OwnershipAssignment(Base, TimestampMixin):
    __tablename__ = "ownership_assignments"
    id: Mapped[UUID] = uuid_column()
    farm_id: Mapped[UUID] = mapped_column(ForeignKey("farms.id"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    assignment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("farm_id", "user_id", "assignment_type"),)


class HealthReport(Base, TimestampMixin):
    __tablename__ = "health_reports"
    id: Mapped[UUID] = uuid_column()
    farm_id: Mapped[UUID] = mapped_column(ForeignKey("farms.id"), index=True)
    animal_id: Mapped[UUID | None] = mapped_column(ForeignKey("animals.id"), index=True)
    herd_id: Mapped[UUID | None] = mapped_column(ForeignKey("herds.id"), index=True)
    reporter_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    species: Mapped[str] = mapped_column(String(20), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    age_band: Mapped[str] = mapped_column(String(20), nullable=False)
    symptom_onset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    appetite: Mapped[str] = mapped_column(String(20), nullable=False)
    water_intake: Mapped[str] = mapped_column(String(20), nullable=False)
    mobility: Mapped[str] = mapped_column(String(24), nullable=False)
    respiration: Mapped[str] = mapped_column(String(20), nullable=False)
    visible_lesions: Mapped[bool | None] = mapped_column(Boolean)
    discharge: Mapped[bool | None] = mapped_column(Boolean)
    temperature_c: Mapped[float | None] = mapped_column(Float)
    vaccination_status: Mapped[str] = mapped_column(String(20), nullable=False)
    recent_movement: Mapped[bool | None] = mapped_column(Boolean)
    recent_contact: Mapped[bool | None] = mapped_column(Boolean)
    mortality_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    village_name: Mapped[str] = mapped_column(String(120), nullable=False)
    location: Mapped[Any | None] = mapped_column(Geography("POINT", srid=4326))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    location_precision: Mapped[str] = mapped_column(String(24), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    voice_transcript: Mapped[str | None] = mapped_column(Text)
    optional_provider_status: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    consent_given: Mapped[bool] = mapped_column(Boolean, nullable=False)
    consent_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="QUEUED_FOR_VET", index=True)
    sync_status: Mapped[str] = mapped_column(String(20), default="SYNCED", nullable=False)
    client_mutation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    created_at_device: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at_server: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    __table_args__ = (
        Index("ix_health_reports_location_gist", "location", postgresql_using="gist"),
        CheckConstraint("mortality_count >= 0", name="mortality_nonnegative"),
        CheckConstraint(
            "temperature_c IS NULL OR temperature_c BETWEEN 25 AND 50", name="temperature"
        ),
        CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="latitude"),
        CheckConstraint("longitude IS NULL OR longitude BETWEEN -180 AND 180", name="longitude"),
        CheckConstraint("consent_given = true", name="consent_required"),
    )


class MortalityReport(Base, TimestampMixin):
    __tablename__ = "mortality_reports"
    id: Mapped[UUID] = uuid_column()
    health_report_id: Mapped[UUID] = mapped_column(ForeignKey("health_reports.id"), unique=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SymptomObservation(Base, TimestampMixin):
    __tablename__ = "symptom_observations"
    id: Mapped[UUID] = uuid_column()
    health_report_id: Mapped[UUID] = mapped_column(ForeignKey("health_reports.id"), index=True)
    symptom_code: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="GUIDED_FORM")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MediaAsset(Base, TimestampMixin):
    __tablename__ = "media_assets"
    id: Mapped[UUID] = uuid_column()
    health_report_id: Mapped[UUID] = mapped_column(ForeignKey("health_reports.id"), index=True)
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    mime_type: Mapped[str] = mapped_column(String(120))
    byte_size: Mapped[int] = mapped_column(Integer)
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    exif_removed: Mapped[bool] = mapped_column(Boolean, default=False)
    upload_status: Mapped[str] = mapped_column(String(24), default="PENDING")
    total_chunks: Mapped[int] = mapped_column(Integer, default=1)
    uploaded_chunks: Mapped[int] = mapped_column(Integer, default=0)


class MediaUploadChunk(Base, TimestampMixin):
    __tablename__ = "media_upload_chunks"
    id: Mapped[UUID] = uuid_column()
    media_asset_id: Mapped[UUID] = mapped_column(ForeignKey("media_assets.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    __table_args__ = (UniqueConstraint("media_asset_id", "chunk_index"),)


class VaccinationRecord(Base, TimestampMixin):
    __tablename__ = "vaccination_records"
    id: Mapped[UUID] = uuid_column()
    animal_id: Mapped[UUID | None] = mapped_column(ForeignKey("animals.id"), index=True)
    herd_id: Mapped[UUID | None] = mapped_column(ForeignKey("herds.id"), index=True)
    vaccine_name: Mapped[str] = mapped_column(String(120))
    administered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))


class TreatmentRecord(Base, TimestampMixin):
    __tablename__ = "treatment_records"
    id: Mapped[UUID] = uuid_column()
    animal_id: Mapped[UUID] = mapped_column(ForeignKey("animals.id"), index=True)
    description: Mapped[str] = mapped_column(Text)
    treated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))


class DiseaseHistory(Base, TimestampMixin):
    __tablename__ = "disease_history"
    id: Mapped[UUID] = uuid_column()
    animal_id: Mapped[UUID] = mapped_column(ForeignKey("animals.id"), index=True)
    reported_condition: Mapped[str] = mapped_column(String(160))
    truth_status: Mapped[str] = mapped_column(String(32), nullable=False)
    verification_reference: Mapped[str | None] = mapped_column(String(200))


class ConsentRecord(Base, TimestampMixin):
    __tablename__ = "consent_records"
    id: Mapped[UUID] = uuid_column()
    health_report_id: Mapped[UUID] = mapped_column(ForeignKey("health_reports.id"), unique=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    consent_version: Mapped[str] = mapped_column(String(32))
    granted_at_device: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at_server: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ModelVersion(Base, TimestampMixin):
    __tablename__ = "model_versions"
    id: Mapped[UUID] = uuid_column()
    name: Mapped[str] = mapped_column(String(120), unique=True)
    modality: Mapped[str] = mapped_column(String(40))
    feature_schema_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(32), default="INACTIVE")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class FeatureSnapshot(Base, TimestampMixin):
    __tablename__ = "feature_snapshots"
    id: Mapped[UUID] = uuid_column()
    health_report_id: Mapped[UUID] = mapped_column(ForeignKey("health_reports.id"), index=True)
    feature_schema_version: Mapped[str] = mapped_column(String(40))
    features: Mapped[dict[str, Any]] = mapped_column(JSONB)


class RiskAssessment(Base, TimestampMixin):
    __tablename__ = "risk_assessments"
    id: Mapped[UUID] = uuid_column()
    health_report_id: Mapped[UUID] = mapped_column(ForeignKey("health_reports.id"), index=True)
    model_version: Mapped[str | None] = mapped_column(String(80))
    rule_version: Mapped[str | None] = mapped_column(String(80))
    feature_schema_version: Mapped[str] = mapped_column(String(40))
    urgency_tier: Mapped[str] = mapped_column(String(24))
    probabilities: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    decision_trace: Mapped[dict[str, Any]] = mapped_column(JSONB)
    preliminary: Mapped[bool] = mapped_column(Boolean, default=True)


class Explanation(Base, TimestampMixin):
    __tablename__ = "explanations"
    id: Mapped[UUID] = uuid_column()
    risk_assessment_id: Mapped[UUID] = mapped_column(ForeignKey("risk_assessments.id"), index=True)
    explanation_type: Mapped[str] = mapped_column(String(40))
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)


class AnalysisArtifact(Base, TimestampMixin):
    """Versioned NLP/CV/context output kept separate from raw observations."""

    __tablename__ = "analysis_artifacts"
    id: Mapped[UUID] = uuid_column()
    health_report_id: Mapped[UUID] = mapped_column(ForeignKey("health_reports.id"), index=True)
    media_asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("media_assets.id"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "health_report_id",
            "artifact_type",
            "input_fingerprint",
            name="analysis_artifact_input",
        ),
    )


class TriageJob(Base, TimestampMixin):
    """Durable retry ledger for the in-process development job adapter."""

    __tablename__ = "triage_jobs"
    id: Mapped[UUID] = uuid_column()
    health_report_id: Mapped[UUID] = mapped_column(ForeignKey("health_reports.id"), index=True)
    job_key: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="PENDING", nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    risk_assessment_id: Mapped[UUID | None] = mapped_column(ForeignKey("risk_assessments.id"))


class VetReview(Base, TimestampMixin):
    __tablename__ = "vet_reviews"
    id: Mapped[UUID] = uuid_column()
    health_report_id: Mapped[UUID] = mapped_column(ForeignKey("health_reports.id"), index=True)
    veterinarian_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    outcome_status: Mapped[str] = mapped_column(String(32))
    verified_label: Mapped[str | None] = mapped_column(String(160))
    notes: Mapped[str | None] = mapped_column(Text)


class CaseAssignment(Base, TimestampMixin):
    __tablename__ = "case_assignments"
    id: Mapped[UUID] = uuid_column()
    health_report_id: Mapped[UUID] = mapped_column(ForeignKey("health_reports.id"), index=True)
    veterinarian_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class StatusHistory(Base, TimestampMixin):
    __tablename__ = "status_history"
    id: Mapped[UUID] = uuid_column()
    health_report_id: Mapped[UUID] = mapped_column(ForeignKey("health_reports.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    actor_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(String(300))


class LabReferral(Base, TimestampMixin):
    __tablename__ = "lab_referrals"
    id: Mapped[UUID] = uuid_column()
    health_report_id: Mapped[UUID] = mapped_column(ForeignKey("health_reports.id"), index=True)
    requested_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    sample_identifier: Mapped[str] = mapped_column(String(120), unique=True)
    status: Mapped[str] = mapped_column(String(32))


class LabResult(Base, TimestampMixin):
    __tablename__ = "lab_results"
    id: Mapped[UUID] = uuid_column()
    lab_referral_id: Mapped[UUID] = mapped_column(ForeignKey("lab_referrals.id"), unique=True)
    result_label: Mapped[str] = mapped_column(String(160))
    result_status: Mapped[str] = mapped_column(String(32))
    recorded_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))


class Advisory(Base, TimestampMixin):
    __tablename__ = "advisories"
    id: Mapped[UUID] = uuid_column()
    health_report_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("health_reports.id"), index=True
    )
    language: Mapped[str] = mapped_column(String(8))
    template_key: Mapped[str] = mapped_column(String(80))
    content: Mapped[str] = mapped_column(Text)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)


class AlertEvent(Base, TimestampMixin):
    __tablename__ = "alert_events"
    id: Mapped[UUID] = uuid_column()
    health_report_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("health_reports.id"), index=True
    )
    alert_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32))
    deduplication_key: Mapped[str] = mapped_column(String(180), unique=True)


class NotificationOutbox(Base, TimestampMixin):
    __tablename__ = "notification_outbox"
    id: Mapped[UUID] = uuid_column()
    alert_event_id: Mapped[UUID | None] = mapped_column(ForeignKey("alert_events.id"), index=True)
    channel: Mapped[str] = mapped_column(String(24))
    recipient_reference: Mapped[str] = mapped_column(String(180))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)


class WeatherSnapshot(Base, TimestampMixin):
    __tablename__ = "weather_snapshots"
    id: Mapped[UUID] = uuid_column()
    location: Mapped[Any] = mapped_column(Geography("POINT", srid=4326))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provider: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    __table_args__ = (Index("ix_weather_location_gist", "location", postgresql_using="gist"),)


class SurveillanceAggregate(Base, TimestampMixin):
    __tablename__ = "surveillance_aggregates"
    id: Mapped[UUID] = uuid_column()
    administrative_area_id: Mapped[UUID] = mapped_column(
        ForeignKey("administrative_areas.id"), index=True
    )
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    syndrome_code: Mapped[str] = mapped_column(String(80))
    suspected_count: Mapped[int] = mapped_column(Integer, default=0)
    verified_count: Mapped[int] = mapped_column(Integer, default=0)
    lab_confirmed_count: Mapped[int] = mapped_column(Integer, default=0)


class DatasetVersion(Base, TimestampMixin):
    __tablename__ = "dataset_versions"
    id: Mapped[UUID] = uuid_column()
    name: Mapped[str] = mapped_column(String(120), unique=True)
    checksum: Mapped[str] = mapped_column(String(64))
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB)
    immutable: Mapped[bool] = mapped_column(Boolean, default=True)


class RetrainingCandidate(Base, TimestampMixin):
    __tablename__ = "retraining_candidates"
    id: Mapped[UUID] = uuid_column()
    health_report_id: Mapped[UUID] = mapped_column(ForeignKey("health_reports.id"), unique=True)
    verification_source: Mapped[str] = mapped_column(String(32))
    verified_label: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), default="STAGED")
    dataset_version_id: Mapped[UUID | None] = mapped_column(ForeignKey("dataset_versions.id"))


class PromotionApproval(Base, TimestampMixin):
    __tablename__ = "promotion_approvals"
    id: Mapped[UUID] = uuid_column()
    model_version_id: Mapped[UUID] = mapped_column(ForeignKey("model_versions.id"), index=True)
    approved_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(32))
    rationale: Mapped[str] = mapped_column(Text)


class SyncMutation(Base):
    __tablename__ = "sync_mutations"
    id: Mapped[UUID] = uuid_column()
    client_mutation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), unique=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    mutation_type: Mapped[str] = mapped_column(String(40))
    actor_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    resource_type: Mapped[str] = mapped_column(String(40))
    resource_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    request_hash: Mapped[str] = mapped_column(String(64))
    result_status: Mapped[str] = mapped_column(String(24))
    base_version: Mapped[int | None] = mapped_column(Integer)
    resource_version: Mapped[int | None] = mapped_column(Integer)
    created_at_device: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at_server: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[UUID] = uuid_column()
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str] = mapped_column(String(60))
    resource_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), index=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64))


class RetentionRequest(Base, TimestampMixin):
    __tablename__ = "retention_requests"
    id: Mapped[UUID] = uuid_column()
    requested_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    resource_type: Mapped[str] = mapped_column(String(60))
    resource_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    requested_action: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="PENDING_REVIEW")
    reason: Mapped[str] = mapped_column(String(300))


class MediaBlob(Base, TimestampMixin):
    """Optional local-dev blob record; production storage stays behind an adapter."""

    __tablename__ = "media_blobs"
    id: Mapped[UUID] = uuid_column()
    media_asset_id: Mapped[UUID] = mapped_column(ForeignKey("media_assets.id"), unique=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
