from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

LanguageCode = Literal["en", "mr", "hi", "unknown"]
UrgencyTier = Literal["LOW", "VET_REVIEW", "EMERGENCY"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceSpan(StrictModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=160)


class SymptomEntity(StrictModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    negated: bool
    body_site: str | None = None
    severity: Literal["MILD", "MODERATE", "SEVERE", "UNKNOWN"] = "UNKNOWN"
    span: SourceSpan | None = None


class SymptomExtraction(StrictModel):
    detected_language: LanguageCode
    normalized_text: str = Field(max_length=4000)
    symptom_entities: list[SymptomEntity] = Field(max_length=40)
    negations: list[str] = Field(max_length=40)
    duration_hours: float | None = Field(default=None, ge=0, le=24 * 365)
    severity: Literal["MILD", "MODERATE", "SEVERE", "UNKNOWN"]
    body_sites: list[str] = Field(max_length=20)
    ambiguous_terms: list[str] = Field(max_length=20)
    uncertain: bool
    parser_confidence: float = Field(ge=0, le=1)
    adapter_version: str
    source: Literal["FREE_TEXT", "VOICE_TRANSCRIPT", "PROVIDER"]


VISIBLE_CLASS_ORDER = [
    "SKIN_LESION",
    "OCULAR_NASAL_DISCHARGE",
    "SWELLING",
    "NORMAL_APPEARANCE",
    "OTHER_UNKNOWN",
]


class ImageQuality(StrictModel):
    accepted: bool
    score: float = Field(ge=0, le=1)
    width: int = Field(ge=0)
    height: int = Field(ge=0)
    blur_score: float = Field(ge=0, le=1)
    exposure_score: float = Field(ge=0, le=1)
    rejection_reasons: list[str]


class VisionPrediction(StrictModel):
    class_order: list[str]
    probabilities: list[float]
    quality: ImageQuality
    uncertainty: float = Field(ge=0, le=1)
    uncertain: bool
    model_version: str
    calibration_status: Literal["DEMO_UNVALIDATED", "CALIBRATED"]

    @model_validator(mode="after")
    def validate_vector(self) -> VisionPrediction:
        if self.class_order != VISIBLE_CLASS_ORDER:
            raise ValueError("vision class order is incompatible")
        if len(self.probabilities) != len(self.class_order):
            raise ValueError("vision probability vector is incomplete")
        if any(value < 0 or value > 1 for value in self.probabilities):
            raise ValueError("vision probabilities must be between zero and one")
        if abs(sum(self.probabilities) - 1.0) > 1e-6:
            raise ValueError("vision probabilities must sum to one")
        return self


class RuleMatch(StrictModel):
    rule_id: str
    version: str
    urgency: UrgencyTier
    reason_code: str
    message: str
    validation_status: Literal["DEMO_UNVALIDATED", "VETERINARIAN_APPROVED"]


class FeatureSnapshotContract(StrictModel):
    feature_schema_version: str
    values: dict[str, float | int | str | bool | None]
    missingness: dict[str, bool]
    source_versions: dict[str, str | None]
    built_at: datetime
    leakage_guard: list[str]


class ExplanationContribution(StrictModel):
    feature: str
    value: float | int | str | bool | None
    contribution: float
    direction: Literal["LOWER", "HIGHER", "NEUTRAL"]
    message: str


class TriageDecision(StrictModel):
    assessment_id: UUID | None = None
    report_id: UUID
    urgency_tier: UrgencyTier
    urgency_probabilities: dict[UrgencyTier, float]
    suspected_condition_likelihoods: dict[str, float]
    rule_matches: list[RuleMatch]
    override_applied: bool
    uncertainty: float = Field(ge=0, le=1)
    insufficient_information: bool
    model_version: str | None
    rule_version: str
    threshold_version: str
    feature_schema_version: str
    calibration_status: Literal["DEMO_UNVALIDATED", "CALIBRATED", "MODEL_UNAVAILABLE"]
    modality_status: dict[str, str]
    contributions: list[ExplanationContribution]
    decision_trace: list[dict[str, Any]]
    clinical_notice: str = (
        "Preliminary triage support only; suspected conditions are not diagnoses. "
        "Veterinary verification is required."
    )


class TriageJobResult(StrictModel):
    job_id: UUID
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED"]
    attempt_count: int
    decision: TriageDecision | None = None
    error_code: str | None = None
