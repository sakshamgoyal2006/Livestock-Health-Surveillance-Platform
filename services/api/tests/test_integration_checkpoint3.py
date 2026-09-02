from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.domain.models import NotificationOutbox, RetrainingCandidate
from app.main import app
from app.operations.alerts import enqueue_alert, process_outbox_item
from app.operations.mlops import stage_retraining_candidate

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


async def create_case(
    client: AsyncClient, farmer: dict[str, str], *, village: str = "Village B"
) -> tuple[UUID, UUID]:
    farm_id, animal_id, report_id = uuid4(), uuid4(), uuid4()
    farm = await client.post(
        "/api/v1/farms",
        headers=farmer,
        json={
            "id": str(farm_id),
            "name": "Synthetic Checkpoint 3 Live Farm",
            "village_name": village,
            "latitude": 18.545,
            "longitude": 73.885,
            "location_precision": "APPROXIMATE",
        },
    )
    assert farm.status_code == 201, farm.text
    animal = await client.post(
        "/api/v1/animals",
        headers=farmer,
        json={
            "id": str(animal_id),
            "farm_id": str(farm_id),
            "herd_id": None,
            "tag_number": f"SYN-CP3-{animal_id.hex[:8]}",
            "species": "CATTLE",
            "sex": "UNKNOWN",
            "age_band": "ADULT",
        },
    )
    assert animal.status_code == 201, animal.text
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "id": str(report_id),
        "farm_id": str(farm_id),
        "animal_id": str(animal_id),
        "herd_id": None,
        "species": "CATTLE",
        "language": "hi",
        "age_band": "ADULT",
        "symptom_onset_at": (now - timedelta(hours=4)).isoformat(),
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
        "village_name": village,
        "latitude": 18.545,
        "longitude": 73.885,
        "location_precision": "APPROXIMATE",
        "notes": "khana kam hai lekin saans samanya hai",
        "media_refs": [],
        "voice_transcript": None,
        "consent_given": True,
        "consent_version": "CP1-3",
        "created_at_device": now.isoformat(),
        "optional_provider_status": {
            "image": "NOT_PROVIDED",
            "voice": "NOT_PROVIDED",
            "nlp": "PENDING",
            "weather": "UNAVAILABLE",
            "ml": "PENDING",
        },
    }
    mutation = {
        "client_mutation_id": str(uuid4()),
        "idempotency_key": f"cp3:{uuid4()}",
        "mutation_type": "CREATE_REPORT",
        "base_version": None,
        "created_at_device": now.isoformat(),
        "payload": payload,
    }
    sync = await client.post("/api/v1/sync/batch", headers=farmer, json={"mutations": [mutation]})
    assert sync.status_code == 200, sync.text
    assert sync.json()["results"][0]["status"] == "APPLIED", sync.text
    vet = await login(client, "VETERINARIAN")
    queue = await client.get("/api/v1/vet/cases?page_size=100", headers=vet)
    item = next(row for row in queue.json()["items"] if row["id"] == str(report_id))
    return report_id, UUID(item["case"]["id"])


async def assign_and_open(
    client: AsyncClient, vet: dict[str, str], case_id: UUID
) -> dict[str, Any]:
    assigned = await client.post(
        f"/api/v1/vet/cases/{case_id}/assign",
        headers=vet,
        json={"expected_version": 1, "veterinarian_user_id": None},
    )
    assert assigned.status_code == 200, assigned.text
    opened = await client.post(
        f"/api/v1/vet/cases/{case_id}/transition",
        headers=vet,
        json={
            "expected_version": 2,
            "to_state": "UNDER_REVIEW",
            "reason": "Reviewing raw evidence",
        },
    )
    assert opened.status_code == 200, opened.text
    return cast(dict[str, Any], opened.json())


async def test_farmer_sync_to_vet_verification_and_immutable_prediction(
    client: AsyncClient,
) -> None:
    farmer = await login(client, "FARMER")
    vet = await login(client, "VETERINARIAN")
    report_id, case_id = await create_case(client, farmer)
    forbidden = await client.get(f"/api/v1/vet/cases/{case_id}", headers=farmer)
    assert forbidden.status_code == 403
    await assign_and_open(client, vet, case_id)
    stale = await client.post(
        f"/api/v1/vet/cases/{case_id}/transition",
        headers=vet,
        json={"expected_version": 2, "to_state": "CLOSED", "reason": "stale data"},
    )
    assert stale.status_code == 409
    reviewed = await client.post(
        f"/api/v1/vet/cases/{case_id}/review",
        headers=vet,
        json={
            "expected_version": 3,
            "outcome": "CORRECTED",
            "verified_label": "RESPIRATORY_SYNDROME",
            "notes": "Authorized synthetic-demo correction",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    evidence = await client.get(f"/api/v1/vet/cases/{case_id}", headers=vet)
    assert evidence.status_code == 200
    body = evidence.json()
    assert body["original_prediction"]["immutable"] is True
    assert body["case"]["suspected_status"] == "PRELIMINARY_SUSPECTED"
    assert body["case"]["verified_status"] == "VET_VERIFIED"
    assert body["case"]["lab_status"] == "NOT_REQUESTED"
    assert body["nearby_context"]["location_missing"] is False
    assert body["original_prediction"]["id"]
    assert body["raw_observations"]["id"] == str(report_id)
    follow_up = await client.post(
        f"/api/v1/vet/cases/{case_id}/follow-ups",
        headers=vet,
        json={"follow_up_type": "PHONE", "notes": "Synthetic follow-up", "due_at": None},
    )
    assert follow_up.status_code == 200
    escalated = await client.post(
        f"/api/v1/vet/cases/{case_id}/escalate",
        headers=vet,
        json={"reason": "Synthetic escalation exercise", "level": 1},
    )
    assert escalated.status_code == 200


async def test_inconclusive_and_lab_confirmed_branches(client: AsyncClient) -> None:
    farmer = await login(client, "FARMER")
    vet = await login(client, "VETERINARIAN")
    _, inconclusive_id = await create_case(client, farmer, village="Synthetic Branch Village")
    await assign_and_open(client, vet, inconclusive_id)
    inconclusive = await client.post(
        f"/api/v1/vet/cases/{inconclusive_id}/review",
        headers=vet,
        json={
            "expected_version": 3,
            "outcome": "INCONCLUSIVE",
            "verified_label": None,
            "notes": "Insufficient observations",
        },
    )
    assert inconclusive.status_code == 200
    assert inconclusive.json()["case"]["verified_status"] == "INCONCLUSIVE"

    _, lab_case_id = await create_case(client, farmer, village="Synthetic Lab Village")
    await assign_and_open(client, vet, lab_case_id)
    sample_id = f"SYN-LAB-{uuid4().hex[:10]}"
    sample = await client.post(
        f"/api/v1/vet/cases/{lab_case_id}/sample-request",
        headers=vet,
        json={"expected_version": 3, "sample_identifier": sample_id},
    )
    assert sample.status_code == 200, sample.text
    assert sample.json()["case"]["state"] == "SAMPLE_REQUESTED"
    pending = await client.post(
        f"/api/v1/vet/cases/{lab_case_id}/transition",
        headers=vet,
        json={
            "expected_version": 4,
            "to_state": "LAB_PENDING",
            "reason": "Synthetic sample received",
        },
    )
    assert pending.status_code == 200
    assert pending.json()["state"] == "LAB_PENDING"
    result = await client.post(
        f"/api/v1/vet/cases/{lab_case_id}/lab-referrals/{sample.json()['referral_id']}/result",
        headers=vet,
        json={
            "expected_version": 5,
            "result_status": "CONFIRMED",
            "result_label": "LAB_SYNTHETIC_POSITIVE",
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["case"]["state"] == "LAB_CONFIRMED"
    assert result.json()["case"]["verified_status"] == "LAB_CONFIRMED"


async def test_gis_aggregates_hotspot_acknowledgement_and_permissions(
    client: AsyncClient,
) -> None:
    officer = await login(client, "DISTRICT_OFFICER")
    farmer = await login(client, "FARMER")
    denied = await client.get("/api/v1/surveillance/aggregates", headers=farmer)
    assert denied.status_code == 403
    aggregate = await client.get("/api/v1/surveillance/aggregates?level=VILLAGE", headers=officer)
    assert aggregate.status_code == 200, aggregate.text
    village_a = next(row for row in aggregate.json()["items"] if row["area_name"] == "Village A")
    assert village_a["suspected_count"] >= 6
    assert village_a["vet_verified_count"] <= village_a["suspected_count"]
    assert "not a confirmed outbreak" in village_a["notice"]
    hotspots = await client.get("/api/v1/surveillance/hotspots", headers=officer)
    candidate = next(row for row in hotspots.json() if row["area_name"] == "Village A")
    assert candidate["status"] in {"CANDIDATE", "ACKNOWLEDGED_CANDIDATE"}
    if candidate["status"] == "CANDIDATE":
        acknowledged = await client.post(
            f"/api/v1/surveillance/hotspots/{candidate['id']}/acknowledge",
            headers=officer,
            json={"note": "Synthetic exercise reviewed"},
        )
        assert acknowledged.json()["status"] == "ACKNOWLEDGED_CANDIDATE"


async def test_alert_dedup_retry_rate_limit_ack_and_development_no_send(
    client: AsyncClient,
) -> None:
    recipient = f"test-recipient:{uuid4()}"
    async with SessionLocal() as session:
        first = await enqueue_alert(
            session,
            deduplication_key=f"retry:{uuid4()}",
            alert_type="TEST_RETRY",
            context={"simulate_transient_failures": 1},
            recipient_reference=recipient,
        )
        duplicate = await enqueue_alert(
            session,
            deduplication_key=first.deduplication_key,
            alert_type="TEST_RETRY",
            context={},
            recipient_reference=recipient,
        )
        assert duplicate.id == first.id
        await session.flush()
        retry_item = await session.scalar(
            select(NotificationOutbox).where(NotificationOutbox.alert_event_id == first.id)
        )
        assert retry_item is not None
        await process_outbox_item(session, retry_item)
        assert retry_item.status == "RETRY_PENDING"
        retry_item.next_attempt_at = None
        await process_outbox_item(session, retry_item)
        assert retry_item.status == "DELIVERED_DEV_NO_SEND"
        assert retry_item.payload["external_send"] is False
        for index in range(3):
            event = await enqueue_alert(
                session,
                deduplication_key=f"rate:{uuid4()}",
                alert_type="TEST_RATE_LIMIT",
                context={"index": index},
                recipient_reference=recipient,
            )
            await session.flush()
            item = await session.scalar(
                select(NotificationOutbox).where(NotificationOutbox.alert_event_id == event.id)
            )
            assert item is not None
            await process_outbox_item(session, item)
        rate_limited = (
            await session.scalars(
                select(NotificationOutbox).where(
                    NotificationOutbox.recipient_reference == recipient,
                    NotificationOutbox.status == "RATE_LIMITED",
                )
            )
        ).all()
        assert rate_limited
        escalation = await enqueue_alert(
            session,
            deduplication_key=f"permanent-failure:{uuid4()}",
            alert_type="TEST_ESCALATION",
            context={"simulate_transient_failures": 2},
            recipient_reference=f"failure-recipient:{uuid4()}",
        )
        await session.flush()
        failed_item = await session.scalar(
            select(NotificationOutbox).where(NotificationOutbox.alert_event_id == escalation.id)
        )
        assert failed_item is not None
        failed_item.max_attempts = 1
        await process_outbox_item(session, failed_item)
        assert failed_item.status == "FAILED_PERMANENT"
        assert escalation.status == "ESCALATED_DEVELOPMENT"
        assert escalation.escalation_level == 1
        await session.commit()
    officer = await login(client, "DISTRICT_OFFICER")
    acknowledged = await client.post(
        f"/api/v1/alerts/{first.id}/acknowledge",
        headers=officer,
        json={"note": "Synthetic alert acknowledged"},
    )
    assert acknowledged.status_code == 200


async def test_verified_only_dataset_regression_promotion_and_rollback(
    client: AsyncClient,
) -> None:
    farmer = await login(client, "FARMER")
    vet = await login(client, "VETERINARIAN")
    admin = await login(client, "ADMIN")
    report_id, case_id = await create_case(client, farmer, village="Synthetic MLOps Village")
    await assign_and_open(client, vet, case_id)
    review = await client.post(
        f"/api/v1/vet/cases/{case_id}/review",
        headers=vet,
        json={
            "expected_version": 3,
            "outcome": "CONFIRMED",
            "verified_label": "SYNTHETIC_VERIFIED_SYNDROME",
            "notes": "Synthetic verified training fixture",
        },
    )
    assert review.status_code == 200
    async with SessionLocal() as session:
        with pytest.raises(ValueError, match="PSEUDO_LABEL_REJECTED"):
            await stage_retraining_candidate(
                session,
                report_id=report_id,
                source=cast(Any, "MODEL_PREDICTION"),
                source_record_id=uuid4(),
                verified_label="PSEUDO_LABEL",
                verifier_user_id=UUID("33333333-3333-4333-8333-333333333333"),
            )
        candidate = await session.scalar(
            select(RetrainingCandidate).where(RetrainingCandidate.health_report_id == report_id)
        )
        assert candidate is not None
        assert candidate.provenance["prediction_used_as_label"] is False
        candidate_id = candidate.id
    quality = await client.post(
        f"/api/v1/mlops/candidates/{candidate_id}/review",
        headers=admin,
        json={"decision": "APPROVED", "note": "Synthetic quality review passed"},
    )
    assert quality.status_code == 200
    dataset = await client.post(
        "/api/v1/mlops/datasets",
        headers=admin,
        json={"name": f"synthetic-dataset-{uuid4()}", "allow_small_synthetic_demo": True},
    )
    assert dataset.status_code == 200, dataset.text
    assert dataset.json()["immutable"] is True
    regressing = await client.post(
        "/api/v1/mlops/models/evaluate",
        headers=admin,
        json={
            "dataset_version_id": dataset.json()["id"],
            "name": f"regression-fixture-{uuid4()}",
            "mode": "INTENTIONAL_REGRESSION_FIXTURE",
        },
    )
    assert regressing.json()["status"] == "REJECTED_REGRESSION"
    rejected_promotion = await client.post(
        f"/api/v1/mlops/models/{regressing.json()['id']}/promote", headers=admin
    )
    assert rejected_promotion.status_code == 409
    candidate = await client.post(
        "/api/v1/mlops/models/evaluate",
        headers=admin,
        json={
            "dataset_version_id": dataset.json()["id"],
            "name": f"baseline-equivalent-{uuid4()}",
            "mode": "BASELINE_EQUIVALENT",
        },
    )
    assert candidate.json()["status"] == "CANDIDATE_EVALUATED"
    no_approval = await client.post(
        f"/api/v1/mlops/models/{candidate.json()['id']}/promote", headers=admin
    )
    assert no_approval.status_code == 409
    approval = await client.post(
        f"/api/v1/mlops/models/{candidate.json()['id']}/approval",
        headers=admin,
        json={"decision": "APPROVED", "rationale": "Synthetic safety gates passed"},
    )
    assert approval.status_code == 200
    promoted = await client.post(
        f"/api/v1/mlops/models/{candidate.json()['id']}/promote", headers=admin
    )
    assert promoted.json()["status"] == "ACTIVE"
    rolled_back = await client.post(
        f"/api/v1/mlops/models/{candidate.json()['id']}/rollback", headers=admin
    )
    assert rolled_back.status_code == 200
    assert rolled_back.json()["status"] == "ACTIVE"
