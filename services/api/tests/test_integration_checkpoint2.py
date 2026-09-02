from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.domain.models import (
    AnalysisArtifact,
    FeatureSnapshot,
    RiskAssessment,
    TriageJob,
)
from app.main import app

pytestmark = pytest.mark.integration

ROLE_EMAILS = {
    "FARMER": "farmer@example.com",
    "VETERINARIAN": "vet@example.com",
    "DISTRICT_OFFICER": "officer@example.com",
}


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def login(client: AsyncClient, role: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/dev-login",
        json={"email": ROLE_EMAILS[role], "role": role, "password": "dev-only"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def subject(client: AsyncClient, headers: dict[str, str]) -> tuple[UUID, UUID]:
    farm_id, animal_id = uuid4(), uuid4()
    farm = await client.post(
        "/api/v1/farms",
        headers=headers,
        json={
            "id": str(farm_id),
            "name": "Synthetic CP2 Farm",
            "village_name": "Synthetic CP2 Village",
            "latitude": 18.5204,
            "longitude": 73.8567,
            "location_precision": "APPROXIMATE",
        },
    )
    assert farm.status_code == 201, farm.text
    animal = await client.post(
        "/api/v1/animals",
        headers=headers,
        json={
            "id": str(animal_id),
            "farm_id": str(farm_id),
            "herd_id": None,
            "tag_number": f"SYN-CP2-{animal_id.hex[:8]}",
            "species": "CATTLE",
            "sex": "UNKNOWN",
            "age_band": "ADULT",
        },
    )
    assert animal.status_code == 201, animal.text
    return farm_id, animal_id


def payload(
    report_id: UUID,
    farm_id: UUID,
    animal_id: UUID,
    **overrides: Any,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    result: dict[str, Any] = {
        "id": str(report_id),
        "farm_id": str(farm_id),
        "animal_id": str(animal_id),
        "herd_id": None,
        "species": "CATTLE",
        "language": "mr",
        "age_band": "ADULT",
        "symptom_onset_at": (now - timedelta(hours=3)).isoformat(),
        "severity": "MODERATE",
        "appetite": "REDUCED",
        "water_intake": "UNKNOWN",
        "mobility": "NORMAL",
        "respiration": "NORMAL",
        "visible_lesions": None,
        "discharge": None,
        "temperature_c": None,
        "vaccination_status": "UNKNOWN",
        "recent_movement": None,
        "recent_contact": None,
        "mortality_count": 0,
        "village_name": "Synthetic CP2 Village",
        "latitude": 18.5204,
        "longitude": 73.8567,
        "location_precision": "APPROXIMATE",
        "notes": "khokla ani nakatun pani",
        "media_refs": [],
        "voice_transcript": "खूप खोकला दोन दिवस",
        "consent_given": True,
        "consent_version": "CP1-1",
        "created_at_device": now.isoformat(),
        "optional_provider_status": {
            "image": "NOT_PROVIDED",
            "voice": "PENDING",
            "nlp": "PENDING",
            "weather": "UNAVAILABLE",
            "ml": "PENDING",
        },
    }
    result.update(overrides)
    return result


async def sync_report(
    client: AsyncClient, headers: dict[str, str], report: dict[str, Any]
) -> dict[str, Any]:
    mutation = {
        "client_mutation_id": str(uuid4()),
        "idempotency_key": f"cp2:{uuid4()}",
        "mutation_type": "CREATE_REPORT",
        "base_version": None,
        "created_at_device": report["created_at_device"],
        "payload": report,
    }
    response = await client.post(
        "/api/v1/sync/batch", headers=headers, json={"mutations": [mutation]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["status"] == "APPLIED"
    return mutation


def accepted_image() -> bytes:
    image = Image.new("RGB", (256, 256))
    pixels = image.load()
    for y in range(256):
        for x in range(256):
            value = 30 if (x // 8 + y // 8) % 2 else 220
            pixels[x, y] = (value, 150, 255 - value)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


async def test_sync_auto_triages_rule_override_and_retry_is_idempotent(
    client: AsyncClient,
) -> None:
    farmer = await login(client, "FARMER")
    farm_id, animal_id = await subject(client, farmer)
    report_id = uuid4()
    await sync_report(
        client,
        farmer,
        payload(report_id, farm_id, animal_id, mortality_count=1, severity="MILD"),
    )

    assessment = await client.get(f"/api/v1/reports/{report_id}/risk-assessment", headers=farmer)
    assert assessment.status_code == 200, assessment.text
    decision = assessment.json()
    assert decision["urgency_tier"] == "EMERGENCY"
    assert decision["override_applied"] is True
    assert decision["rule_matches"][0]["validation_status"] == "DEMO_UNVALIDATED"
    assert decision["modality_status"]["guided_form"] == "PRIMARY"
    assert "not diagnoses" in decision["clinical_notice"]

    first_id = decision["assessment_id"]
    for _ in range(2):
        retry = await client.post(f"/api/v1/reports/{report_id}/triage", headers=farmer)
        assert retry.status_code == 200, retry.text
        assert retry.json()["status"] == "COMPLETED"
        assert retry.json()["decision"]["assessment_id"] == first_id

    vet_queue = await client.get("/api/v1/vet/cases", headers=await login(client, "VETERINARIAN"))
    item = next(row for row in vet_queue.json()["items"] if row["id"] == str(report_id))
    assert item["risk_assessment"]["urgency_tier"] == "EMERGENCY"

    async with SessionLocal() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(RiskAssessment)
                .where(RiskAssessment.health_report_id == report_id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(TriageJob)
                .where(TriageJob.health_report_id == report_id)
            )
            == 1
        )


async def test_form_only_missingness_and_risk_authorization(client: AsyncClient) -> None:
    farmer = await login(client, "FARMER")
    farm_id, animal_id = await subject(client, farmer)
    report_id = uuid4()
    await sync_report(
        client,
        farmer,
        payload(
            report_id,
            farm_id,
            animal_id,
            notes=None,
            voice_transcript=None,
            latitude=None,
            longitude=None,
            location_precision="VILLAGE_ONLY",
        ),
    )
    result = (
        await client.get(f"/api/v1/reports/{report_id}/risk-assessment", headers=farmer)
    ).json()
    assert result["urgency_tier"] == "VET_REVIEW"
    assert result["modality_status"]["nlp"] == "NOT_PROVIDED"
    assert result["modality_status"]["vision"] == "NOT_PROVIDED"
    assert result["insufficient_information"] is True
    officer = await login(client, "DISTRICT_OFFICER")
    assert (
        await client.get(f"/api/v1/reports/{report_id}/risk-assessment", headers=officer)
    ).status_code == 403
    async with SessionLocal() as session:
        snapshot = await session.scalar(
            select(FeatureSnapshot)
            .where(FeatureSnapshot.health_report_id == report_id)
            .order_by(FeatureSnapshot.created_at.desc())
        )
        assert snapshot is not None
        assert snapshot.features["values"]["vision_quality"] is None
        assert snapshot.features["missingness"]["vision_missing"] is True
        assert snapshot.features["missingness"]["weather_missing"] is True


async def test_completed_image_triggers_quality_checked_versioned_retriage(
    client: AsyncClient,
) -> None:
    farmer = await login(client, "FARMER")
    farm_id, animal_id = await subject(client, farmer)
    report_id = uuid4()
    await sync_report(client, farmer, payload(report_id, farm_id, animal_id))
    content = accepted_image()
    asset_id = uuid4()
    upload = await client.post(
        "/api/v1/media/presign-or-upload",
        headers=farmer,
        data={
            "asset_id": str(asset_id),
            "report_id": str(report_id),
            "chunk_index": "0",
            "total_chunks": "1",
            "checksum_sha256": hashlib.sha256(content).hexdigest(),
        },
        files={"file": ("synthetic-cp2.png", content, "image/png")},
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["complete"] is True

    decision = (
        await client.get(f"/api/v1/reports/{report_id}/risk-assessment", headers=farmer)
    ).json()
    assert decision["modality_status"]["vision"] == "AVAILABLE"
    assert "OTHER_UNKNOWN" in decision["suspected_condition_likelihoods"]
    assert decision["model_version"].startswith("interpretable-risk-demo")
    assert decision["feature_schema_version"] == "triage-features-v1.0.0"
    async with SessionLocal() as session:
        artifacts = (
            await session.scalars(
                select(AnalysisArtifact).where(
                    AnalysisArtifact.health_report_id == report_id,
                    AnalysisArtifact.artifact_type == "VISION",
                )
            )
        ).all()
        assert len(artifacts) == 1
        assert artifacts[0].payload["class_order"][-1] == "OTHER_UNKNOWN"
        assert sum(artifacts[0].payload["probabilities"]) == pytest.approx(1.0)
