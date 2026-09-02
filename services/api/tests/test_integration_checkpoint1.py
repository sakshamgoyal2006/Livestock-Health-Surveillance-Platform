from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import func, select, text

from app.db.session import SessionLocal
from app.domain.models import AuditLog, ConsentRecord, HealthReport, SyncMutation
from app.main import app

pytestmark = pytest.mark.integration

ROLE_EMAILS = {
    "FARMER": "farmer@example.com",
    "FIELD_WORKER": "field@example.com",
    "VETERINARIAN": "vet@example.com",
    "DISTRICT_OFFICER": "officer@example.com",
    "ADMIN": "admin@example.com",
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


async def create_subject(client: AsyncClient, headers: dict[str, str]) -> tuple[UUID, UUID]:
    farm_id, animal_id = uuid4(), uuid4()
    farm = await client.post(
        "/api/v1/farms",
        headers=headers,
        json={
            "id": str(farm_id),
            "name": "Synthetic Integration Farm",
            "village_name": "Synthetic Integration Village",
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
            "tag_number": f"SYN-{animal_id.hex[:8]}",
            "species": "CATTLE",
            "sex": "UNKNOWN",
            "age_band": "ADULT",
        },
    )
    assert animal.status_code == 201, animal.text
    return farm_id, animal_id


def report_payload(report_id: UUID, farm_id: UUID, animal_id: UUID) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "id": str(report_id),
        "farm_id": str(farm_id),
        "animal_id": str(animal_id),
        "herd_id": None,
        "species": "CATTLE",
        "language": "en",
        "age_band": "ADULT",
        "symptom_onset_at": (now - timedelta(hours=2)).isoformat(),
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
        "village_name": "Synthetic Integration Village",
        "latitude": 18.5204,
        "longitude": 73.8567,
        "location_precision": "APPROXIMATE",
        "notes": None,
        "media_refs": [],
        "voice_transcript": None,
        "consent_given": True,
        "consent_version": "CP1-1",
        "created_at_device": now.isoformat(),
        "optional_provider_status": {
            "image": "UNAVAILABLE",
            "voice": "UNAVAILABLE",
            "nlp": "UNAVAILABLE",
            "weather": "UNAVAILABLE",
            "ml": "UNAVAILABLE",
        },
    }


def mutation(payload: dict[str, Any], *, base_version: int | None = None) -> dict[str, Any]:
    return {
        "client_mutation_id": str(uuid4()),
        "idempotency_key": f"test:{uuid4()}",
        "mutation_type": "CREATE_REPORT" if base_version is None else "UPDATE_REPORT",
        "base_version": base_version,
        "created_at_device": payload.get("created_at_device", datetime.now(UTC).isoformat()),
        "payload": payload,
    }


@pytest.mark.parametrize("role", list(ROLE_EMAILS))
async def test_every_role_can_authenticate_and_read_me(client: AsyncClient, role: str) -> None:
    headers = await login(client, role)
    response = await client.get("/api/v1/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["role"] == role


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("FARMER", 201),
        ("FIELD_WORKER", 201),
        ("VETERINARIAN", 403),
        ("DISTRICT_OFFICER", 403),
        ("ADMIN", 201),
    ],
)
async def test_registry_write_authorization(client: AsyncClient, role: str, expected: int) -> None:
    response = await client.post(
        "/api/v1/farms",
        headers=await login(client, role),
        json={
            "id": str(uuid4()),
            "name": "Synthetic Authorization Farm",
            "village_name": "Synthetic Village",
            "latitude": None,
            "longitude": None,
            "location_precision": "VILLAGE_ONLY",
        },
    )
    assert response.status_code == expected


@pytest.mark.parametrize(
    ("role", "queue_status", "audit_status"),
    [
        ("FARMER", 403, 403),
        ("FIELD_WORKER", 403, 403),
        ("VETERINARIAN", 200, 403),
        ("DISTRICT_OFFICER", 403, 403),
        ("ADMIN", 200, 200),
    ],
)
async def test_queue_and_audit_authorization(
    client: AsyncClient, role: str, queue_status: int, audit_status: int
) -> None:
    headers = await login(client, role)
    assert (await client.get("/api/v1/vet/cases", headers=headers)).status_code == queue_status
    assert (await client.get("/api/v1/admin/audit", headers=headers)).status_code == audit_status


async def test_two_reports_sync_exactly_once_with_postgis_consent_and_audit(
    client: AsyncClient,
) -> None:
    farmer = await login(client, "FARMER")
    farm_id, animal_id = await create_subject(client, farmer)
    report_ids = [uuid4(), uuid4()]
    mutations = [
        mutation(report_payload(report_id, farm_id, animal_id)) for report_id in report_ids
    ]

    first = await client.post("/api/v1/sync/batch", headers=farmer, json={"mutations": mutations})
    assert first.status_code == 200, first.text
    assert [item["status"] for item in first.json()["results"]] == ["APPLIED", "APPLIED"]

    retry = await client.post("/api/v1/sync/batch", headers=farmer, json={"mutations": mutations})
    assert retry.status_code == 200
    assert [item["status"] for item in retry.json()["results"]] == ["DUPLICATE", "DUPLICATE"]

    vet_queue = await client.get(
        "/api/v1/vet/cases?page_size=100", headers=await login(client, "VETERINARIAN")
    )
    assert vet_queue.status_code == 200
    queue_ids = [item["id"] for item in vet_queue.json()["items"]]
    for report_id in report_ids:
        assert queue_ids.count(str(report_id)) == 1

    async with SessionLocal() as session:
        count = await session.scalar(
            select(func.count()).select_from(HealthReport).where(HealthReport.id.in_(report_ids))
        )
        assert count == 2
        sync_count = await session.scalar(
            select(func.count())
            .select_from(SyncMutation)
            .where(SyncMutation.resource_id.in_(report_ids))
        )
        assert sync_count == 2
        consent_count = await session.scalar(
            select(func.count())
            .select_from(ConsentRecord)
            .where(ConsentRecord.health_report_id.in_(report_ids))
        )
        assert consent_count == 2
        audit_count = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.resource_id.in_(report_ids),
                AuditLog.action == "REPORT_SYNCHRONIZED",
            )
        )
        assert audit_count == 2
        point = await session.scalar(
            text("SELECT ST_AsText(location::geometry) FROM health_reports WHERE id = :id"),
            {"id": report_ids[0]},
        )
        assert point == "POINT(73.8567 18.5204)"
        report = await session.get(HealthReport, report_ids[0])
        assert report is not None
        assert report.temperature_c is None
        assert report.voice_transcript is None
        assert set(report.optional_provider_status.values()) == {"UNAVAILABLE"}
        assert report.created_at_device <= report.received_at_server


async def test_invalid_report_is_rejected_without_losing_mutation_identity(
    client: AsyncClient,
) -> None:
    farmer = await login(client, "FARMER")
    farm_id, animal_id = await create_subject(client, farmer)
    payload = report_payload(uuid4(), farm_id, animal_id)
    payload["consent_given"] = False
    item = mutation(payload)
    response = await client.post("/api/v1/sync/batch", headers=farmer, json={"mutations": [item]})
    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "REJECTED"
    assert response.json()["results"][0]["error"]["code"] == "INVALID_REPORT"
    replay = await client.post("/api/v1/sync/batch", headers=farmer, json={"mutations": [item]})
    assert replay.json()["results"][0]["status"] == "REJECTED"


async def test_stale_update_returns_conflict_and_does_not_change_report(
    client: AsyncClient,
) -> None:
    farmer = await login(client, "FARMER")
    farm_id, animal_id = await create_subject(client, farmer)
    report_id = uuid4()
    created = mutation(report_payload(report_id, farm_id, animal_id))
    assert (
        await client.post("/api/v1/sync/batch", headers=farmer, json={"mutations": [created]})
    ).json()["results"][0]["status"] == "APPLIED"

    stale = mutation(
        {"id": str(report_id), "severity": "SEVERE", "notes": "stale client edit"},
        base_version=99,
    )
    response = await client.post("/api/v1/sync/batch", headers=farmer, json={"mutations": [stale]})
    assert response.json()["results"][0]["status"] == "CONFLICT"
    assert response.json()["results"][0]["error"]["code"] == "STALE_VERSION"
    report = await client.get(f"/api/v1/reports/{report_id}", headers=farmer)
    assert report.json()["severity"] == "MODERATE"
    assert report.json()["version"] == 1


async def test_readiness_proves_postgis_connectivity(client: AsyncClient) -> None:
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "postgresql"
    assert response.json()["postgis"]


async def test_optional_media_is_resumable_sanitized_and_authorized(client: AsyncClient) -> None:
    farmer = await login(client, "FARMER")
    farm_id, animal_id = await create_subject(client, farmer)
    report_id = uuid4()
    created = mutation(report_payload(report_id, farm_id, animal_id))
    response = await client.post(
        "/api/v1/sync/batch", headers=farmer, json={"mutations": [created]}
    )
    assert response.json()["results"][0]["status"] == "APPLIED"

    image_buffer = BytesIO()
    exif = Image.Exif()
    exif[0x010E] = "synthetic test metadata"
    Image.new("RGB", (8, 8), color=(15, 80, 65)).save(image_buffer, format="JPEG", exif=exif)
    image_bytes = image_buffer.getvalue()
    asset_id = uuid4()
    form = {
        "asset_id": str(asset_id),
        "report_id": str(report_id),
        "chunk_index": "0",
        "total_chunks": "1",
        "checksum_sha256": hashlib.sha256(image_bytes).hexdigest(),
    }
    uploaded = await client.post(
        "/api/v1/media/presign-or-upload",
        headers=farmer,
        data=form,
        files={"file": ("synthetic.jpg", image_bytes, "image/jpeg")},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["status"] == "COMPLETE"
    duplicate = await client.post(
        "/api/v1/media/presign-or-upload",
        headers=farmer,
        data=form,
        files={"file": ("synthetic.jpg", image_bytes, "image/jpeg")},
    )
    assert duplicate.status_code == 200

    assert (await client.get(f"/api/v1/media/{asset_id}", headers=farmer)).status_code == 200
    assert (
        await client.get(f"/api/v1/media/{asset_id}", headers=await login(client, "VETERINARIAN"))
    ).status_code == 200
    assert (
        await client.get(f"/api/v1/media/{asset_id}", headers=await login(client, "FIELD_WORKER"))
    ).status_code == 404
    assert (
        await client.get(
            f"/api/v1/media/{asset_id}", headers=await login(client, "DISTRICT_OFFICER")
        )
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/media/{asset_id}", headers=await login(client, "ADMIN"))
    ).status_code == 200
