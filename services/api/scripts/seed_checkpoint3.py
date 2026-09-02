from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.domain.models import (
    AdministrativeArea,
    Farm,
    HealthReport,
    ModelVersion,
    User,
    WeatherSnapshot,
)
from app.operations.mlops import CURRENT_MODEL_NAME, FEATURE_SCHEMA_VERSION, _evaluate
from app.operations.surveillance import refresh_hotspot_candidates

DISTRICT_ID = UUID("60000000-0000-4000-8000-000000000001")
BLOCK_ID = UUID("60000000-0000-4000-8000-000000000002")
VILLAGE_A_ID = UUID("60000000-0000-4000-8000-00000000000a")
VILLAGE_B_ID = UUID("60000000-0000-4000-8000-00000000000b")
FARM_A_ID = UUID("70000000-0000-4000-8000-00000000000a")
FARM_B_ID = UUID("70000000-0000-4000-8000-00000000000b")
FARMER_ID = UUID("11111111-1111-4111-8111-111111111111")


async def _area(
    session: AsyncSession, area_id: UUID, name: str, level: str, parent: UUID | None
) -> None:
    row = await session.get(AdministrativeArea, area_id)
    if row is None:
        session.add(AdministrativeArea(id=area_id, name=name, level=level, parent_id=parent))


def _report_values(
    report_id: UUID,
    farm_id: UUID,
    village: str,
    latitude: float,
    longitude: float,
    observed_at: datetime,
    severity: str,
) -> dict[str, object]:
    return {
        "id": report_id,
        "farm_id": farm_id,
        "reporter_user_id": FARMER_ID,
        "species": "CATTLE",
        "language": "mr",
        "age_band": "ADULT",
        "symptom_onset_at": observed_at - timedelta(hours=6),
        "severity": severity,
        "appetite": "REDUCED",
        "water_intake": "NORMAL",
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
        "location": f"SRID=4326;POINT({longitude} {latitude})",
        "latitude": latitude,
        "longitude": longitude,
        "location_precision": "APPROXIMATE",
        "notes": "स्पष्टपणे कृत्रिम कालक्रमिक देखरेख नमुना",
        "voice_transcript": None,
        "optional_provider_status": {
            "image": "NOT_PROVIDED",
            "voice": "NOT_PROVIDED",
            "nlp": "UNAVAILABLE",
            "weather": "UNAVAILABLE",
            "ml": "UNAVAILABLE",
        },
        "consent_given": True,
        "consent_version": "synthetic-demo-v1",
        "status": "QUEUED_FOR_VET",
        "sync_status": "SYNCED",
        "client_mutation_id": report_id,
        "idempotency_key": f"synthetic-checkpoint3-{report_id}",
        "created_at_device": observed_at - timedelta(minutes=3),
        "received_at_server": observed_at,
        "version": 1,
    }


async def seed() -> None:
    clock = datetime.now(UTC)
    async with SessionLocal() as session:
        farmer = await session.get(User, FARMER_ID)
        if farmer is None:
            raise RuntimeError("Run python -m scripts.seed before the Checkpoint 3 seed")
        await _area(session, DISTRICT_ID, "Synthetic District", "DISTRICT", None)
        await _area(session, BLOCK_ID, "Synthetic Block", "BLOCK", DISTRICT_ID)
        await _area(session, VILLAGE_A_ID, "Village A", "VILLAGE", BLOCK_ID)
        await _area(session, VILLAGE_B_ID, "Village B", "VILLAGE", BLOCK_ID)
        await session.flush()
        farms = [
            (FARM_A_ID, "Synthetic Village A Farm", "Village A", VILLAGE_A_ID, 18.520, 73.856),
            (FARM_B_ID, "Synthetic Village B Farm", "Village B", VILLAGE_B_ID, 18.545, 73.885),
        ]
        for farm_id, name, village, area_id, latitude, longitude in farms:
            farm = await session.get(Farm, farm_id)
            if farm is None:
                session.add(
                    Farm(
                        id=farm_id,
                        owner_user_id=FARMER_ID,
                        name=name,
                        village_name=village,
                        administrative_area_id=area_id,
                        location=f"SRID=4326;POINT({longitude} {latitude})",
                        latitude=latitude,
                        longitude=longitude,
                        location_precision="APPROXIMATE",
                        synthetic=True,
                    )
                )
        scenarios = [
            # Historical low baseline for both villages.
            (
                "80000000-0000-4000-8000-000000000001",
                FARM_A_ID,
                "Village A",
                18.520,
                73.856,
                clock - timedelta(days=10),
                "MILD",
            ),
            (
                "80000000-0000-4000-8000-000000000002",
                FARM_B_ID,
                "Village B",
                18.545,
                73.885,
                clock - timedelta(days=9),
                "MILD",
            ),
            # Day 1: small suspected signal in Village A.
            (
                "80000000-0000-4000-8000-000000000011",
                FARM_A_ID,
                "Village A",
                18.521,
                73.857,
                clock - timedelta(hours=36),
                "MODERATE",
            ),
            (
                "80000000-0000-4000-8000-000000000012",
                FARM_A_ID,
                "Village A",
                18.519,
                73.855,
                clock - timedelta(hours=32),
                "MODERATE",
            ),
            # Day 2: meaningful rise in Village A and one nearby Village B report.
            (
                "80000000-0000-4000-8000-000000000021",
                FARM_A_ID,
                "Village A",
                18.522,
                73.858,
                clock - timedelta(hours=15),
                "MODERATE",
            ),
            (
                "80000000-0000-4000-8000-000000000022",
                FARM_A_ID,
                "Village A",
                18.518,
                73.854,
                clock - timedelta(hours=13),
                "SEVERE",
            ),
            (
                "80000000-0000-4000-8000-000000000023",
                FARM_A_ID,
                "Village A",
                18.523,
                73.859,
                clock - timedelta(hours=11),
                "MODERATE",
            ),
            (
                "80000000-0000-4000-8000-000000000024",
                FARM_A_ID,
                "Village A",
                18.517,
                73.853,
                clock - timedelta(hours=9),
                "MODERATE",
            ),
            (
                "80000000-0000-4000-8000-00000000002b",
                FARM_B_ID,
                "Village B",
                18.544,
                73.884,
                clock - timedelta(hours=8),
                "MODERATE",
            ),
        ]
        for raw_id, farm_id, village, latitude, longitude, observed, severity in scenarios:
            report_id = UUID(raw_id)
            report = await session.get(HealthReport, report_id)
            values = _report_values(
                report_id, farm_id, village, latitude, longitude, observed, severity
            )
            if report is None:
                session.add(HealthReport(**values))
            else:
                # Keep the explicitly synthetic chronology fresh and reproducible on rerun.
                report.received_at_server = observed
                report.created_at_device = observed - timedelta(minutes=3)
                report.symptom_onset_at = observed - timedelta(hours=6)
        current = await session.scalar(
            select(ModelVersion).where(ModelVersion.name == CURRENT_MODEL_NAME)
        )
        if current is None:
            session.add(
                ModelVersion(
                    name=CURRENT_MODEL_NAME,
                    modality="RISK",
                    feature_schema_version=FEATURE_SCHEMA_VERSION,
                    status="ACTIVE",
                    metadata_json={
                        "locked_benchmark_metrics": _evaluate("BASELINE_EQUIVALENT"),
                        "provenance": "SYNTHETIC_DEMO_LOCKED_BENCHMARK",
                        "clinical_validation": False,
                    },
                )
            )
        weather = await session.scalar(
            select(WeatherSnapshot).where(WeatherSnapshot.provider == "SYNTHETIC_CACHED_DEMO")
        )
        if weather is None:
            session.add(
                WeatherSnapshot(
                    location="SRID=4326;POINT(73.856 18.520)",
                    observed_at=clock - timedelta(hours=1),
                    provider="SYNTHETIC_CACHED_DEMO",
                    payload={"temperature_c": 27.0, "humidity_pct": 72.0, "synthetic": True},
                )
            )
        await session.flush()
        candidates = await refresh_hotspot_candidates(session, now=clock)
        await session.commit()
    print(
        "Loaded explicitly SYNTHETIC Village A/B chronology, cached weather, "
        f"demo model baseline, and {len(candidates)} hotspot candidate(s)."
    )


if __name__ == "__main__":
    asyncio.run(seed())
