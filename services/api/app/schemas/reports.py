from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.common import APIModel
from app.schemas.registry import CoordinatesMixin, SpeciesValue


class OptionalProviderStatus(APIModel):
    image: Literal["NOT_PROVIDED", "PENDING", "UNAVAILABLE"] = "NOT_PROVIDED"
    voice: Literal["NOT_PROVIDED", "PENDING", "UNAVAILABLE"] = "NOT_PROVIDED"
    nlp: Literal["PENDING", "UNAVAILABLE"] = "UNAVAILABLE"
    weather: Literal["PENDING", "UNAVAILABLE"] = "UNAVAILABLE"
    ml: Literal["PENDING", "UNAVAILABLE"] = "UNAVAILABLE"


class ReportPayload(CoordinatesMixin):
    id: UUID
    farm_id: UUID
    animal_id: UUID | None = None
    herd_id: UUID | None = None
    species: SpeciesValue
    language: Literal["en", "mr", "hi"] = "en"
    age_band: Literal["CALF", "YOUNG", "ADULT", "UNKNOWN"]
    symptom_onset_at: datetime
    severity: Literal["MILD", "MODERATE", "SEVERE"]
    appetite: Literal["NORMAL", "REDUCED", "NONE", "UNKNOWN"]
    water_intake: Literal["NORMAL", "REDUCED", "NONE", "UNKNOWN"]
    mobility: Literal["NORMAL", "LIMPING", "UNABLE_TO_STAND", "UNKNOWN"]
    respiration: Literal["NORMAL", "DIFFICULT", "RAPID", "UNKNOWN"]
    visible_lesions: bool | None = None
    discharge: bool | None = None
    temperature_c: float | None = Field(default=None, ge=25, le=50)
    vaccination_status: Literal["CURRENT", "OVERDUE", "UNKNOWN"]
    recent_movement: bool | None = None
    recent_contact: bool | None = None
    mortality_count: int = Field(default=0, ge=0, le=100000)
    village_name: str = Field(min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)
    media_refs: list[str] = Field(default_factory=list, max_length=10)
    voice_transcript: str | None = Field(default=None, max_length=4000)
    consent_given: Literal[True]
    consent_version: str = Field(pattern=r"^CP1-\d+$", max_length=32)
    created_at_device: datetime
    optional_provider_status: OptionalProviderStatus = Field(default_factory=OptionalProviderStatus)

    @model_validator(mode="after")
    def validate_report(self) -> ReportPayload:
        if self.animal_id is None and self.herd_id is None:
            raise ValueError("an animal_id or herd_id is required")
        now = datetime.now(UTC)
        onset = self.symptom_onset_at.astimezone(UTC)
        device_time = self.created_at_device.astimezone(UTC)
        if onset > now + timedelta(minutes=5):
            raise ValueError("symptom onset cannot be in the future")
        if device_time > now + timedelta(minutes=10):
            raise ValueError("device timestamp is too far in the future")
        return self


class SyncMutationIn(APIModel):
    client_mutation_id: UUID
    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    mutation_type: Literal["CREATE_REPORT", "UPDATE_REPORT"]
    base_version: int | None = Field(default=None, ge=1)
    created_at_device: datetime
    payload: dict[str, Any]

    @model_validator(mode="after")
    def update_requires_version(self) -> SyncMutationIn:
        if self.mutation_type == "UPDATE_REPORT" and self.base_version is None:
            raise ValueError("UPDATE_REPORT requires base_version")
        return self


class SyncBatchRequest(APIModel):
    mutations: list[SyncMutationIn] = Field(min_length=1, max_length=50)


class ReportOut(APIModel):
    id: UUID
    farm_id: UUID
    animal_id: UUID | None
    herd_id: UUID | None
    reporter_user_id: UUID
    species: str
    language: str
    age_band: str
    symptom_onset_at: datetime
    severity: str
    appetite: str
    water_intake: str
    mobility: str
    respiration: str
    visible_lesions: bool | None
    discharge: bool | None
    temperature_c: float | None
    vaccination_status: str
    recent_movement: bool | None
    recent_contact: bool | None
    mortality_count: int
    village_name: str
    latitude: float | None
    longitude: float | None
    location_precision: str
    notes: str | None
    voice_transcript: str | None
    optional_provider_status: dict[str, Any]
    consent_given: bool
    consent_version: str
    status: str
    sync_status: str
    client_mutation_id: UUID
    idempotency_key: str
    created_at_device: datetime
    received_at_server: datetime
    updated_at: datetime
    version: int


class ReportUpdate(APIModel):
    id: UUID
    severity: Literal["MILD", "MODERATE", "SEVERE"] | None = None
    notes: str | None = Field(default=None, max_length=4000)


class TimelineEvent(APIModel):
    occurred_at: datetime
    event_type: str
    actor_user_id: UUID | None
    details: dict[str, Any]
