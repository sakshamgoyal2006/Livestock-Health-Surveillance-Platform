from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VersionedBody(StrictBody):
    expected_version: int = Field(ge=1)


class AssignCaseIn(VersionedBody):
    veterinarian_user_id: UUID | None = None


class TransitionCaseIn(VersionedBody):
    to_state: Literal["UNDER_REVIEW", "LAB_PENDING", "CLOSED"]
    reason: str = Field(min_length=3, max_length=300)


class VetReviewIn(VersionedBody):
    outcome: Literal["CONFIRMED", "CORRECTED", "INCONCLUSIVE"]
    verified_label: str | None = Field(default=None, min_length=2, max_length=160)
    notes: str | None = Field(default=None, max_length=2000)


class SampleRequestIn(VersionedBody):
    sample_identifier: str = Field(min_length=4, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")


class LabResultIn(VersionedBody):
    result_status: Literal["CONFIRMED", "NEGATIVE", "INCONCLUSIVE"]
    result_label: str = Field(min_length=2, max_length=160)


class FollowUpIn(StrictBody):
    follow_up_type: Literal["PHONE", "FIELD_VISIT", "TREATMENT_CHECK", "OTHER"]
    notes: str = Field(min_length=2, max_length=2000)
    due_at: datetime | None = None


class EscalateIn(StrictBody):
    reason: str = Field(min_length=3, max_length=300)
    level: int = Field(ge=1, le=3)


class AcknowledgeIn(StrictBody):
    note: str | None = Field(default=None, max_length=500)


class CandidateReviewIn(StrictBody):
    decision: Literal["APPROVED", "REJECTED"]
    note: str = Field(min_length=3, max_length=500)


class DatasetBuildIn(StrictBody):
    name: str = Field(min_length=4, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")
    allow_small_synthetic_demo: bool = False


class CandidateEvaluationIn(StrictBody):
    dataset_version_id: UUID
    name: str = Field(min_length=4, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")
    mode: Literal["BASELINE_EQUIVALENT", "INTENTIONAL_REGRESSION_FIXTURE"]


class PromotionApprovalIn(StrictBody):
    decision: Literal["APPROVED", "REJECTED"]
    rationale: str = Field(min_length=4, max_length=2000)
