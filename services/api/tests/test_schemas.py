from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.logging import safe_log_context
from app.schemas.registry import FarmCreate
from app.schemas.reports import ReportPayload


def valid_report() -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "id": uuid4(),
        "farm_id": uuid4(),
        "animal_id": uuid4(),
        "herd_id": None,
        "species": "CATTLE",
        "language": "en",
        "age_band": "ADULT",
        "symptom_onset_at": now - timedelta(hours=2),
        "severity": "MILD",
        "appetite": "UNKNOWN",
        "water_intake": "UNKNOWN",
        "mobility": "UNKNOWN",
        "respiration": "UNKNOWN",
        "visible_lesions": None,
        "discharge": None,
        "temperature_c": None,
        "vaccination_status": "UNKNOWN",
        "recent_movement": None,
        "recent_contact": None,
        "mortality_count": 0,
        "village_name": "Synthetic Village",
        "latitude": None,
        "longitude": None,
        "location_precision": "VILLAGE_ONLY",
        "notes": None,
        "media_refs": [],
        "voice_transcript": None,
        "consent_given": True,
        "consent_version": "CP1-1",
        "created_at_device": now,
        "optional_provider_status": {
            "image": "NOT_PROVIDED",
            "voice": "NOT_PROVIDED",
            "nlp": "UNAVAILABLE",
            "weather": "UNAVAILABLE",
            "ml": "UNAVAILABLE",
        },
    }


def test_report_accepts_missing_optional_fields_as_null() -> None:
    report = ReportPayload.model_validate(valid_report())
    assert report.temperature_c is None
    assert report.visible_lesions is None
    assert report.voice_transcript is None


@pytest.mark.parametrize(
    ("field", "value"),
    [("temperature_c", 80), ("mortality_count", -1), ("consent_given", False)],
)
def test_report_rejects_invalid_inputs(field: str, value: object) -> None:
    payload = valid_report()
    payload[field] = value
    with pytest.raises(ValidationError):
        ReportPayload.model_validate(payload)


def test_report_rejects_future_onset() -> None:
    payload = valid_report()
    payload["symptom_onset_at"] = datetime.now(UTC) + timedelta(hours=1)
    with pytest.raises(ValidationError, match="future"):
        ReportPayload.model_validate(payload)


def test_coordinates_must_be_paired() -> None:
    with pytest.raises(ValidationError, match="supplied together"):
        FarmCreate(
            id=uuid4(),
            name="Synthetic Farm",
            village_name="Synthetic Village",
            latitude=18.5,
            longitude=None,
            location_precision="APPROXIMATE",
        )


def test_log_context_redacts_sensitive_values() -> None:
    context = safe_log_context(password="secret", notes="animal detail", request_id="safe")
    assert context == {"password": "[REDACTED]", "notes": "[REDACTED]", "request_id": "safe"}
