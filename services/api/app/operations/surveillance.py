from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    AdministrativeArea,
    Farm,
    HealthReport,
    HotspotCandidate,
    RiskAssessment,
    VeterinaryCase,
    WeatherSnapshot,
)
from app.operations.alerts import enqueue_alert

DETECTOR_VERSION = "rolling-baseline-demo-1.0.0"
WINDOW_DAYS = 2
BASELINE_DAYS = 14
MINIMUM_CASES = 3
MINIMUM_LIFT = 2.0
PROXIMITY_METERS = 10_000


class CachedWeatherAdapter:
    version = "cached-weather-db-1.0.0"

    async def nearby(
        self, session: AsyncSession, *, latitude: float | None, longitude: float | None
    ) -> dict[str, Any]:
        if latitude is None or longitude is None:
            return {"status": "MISSING", "version": self.version, "snapshot": None}
        point = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)
        row = await session.scalar(
            select(WeatherSnapshot)
            .where(func.ST_DWithin(WeatherSnapshot.location, point, 50_000))
            .order_by(WeatherSnapshot.observed_at.desc())
            .limit(1)
        )
        return {
            "status": "AVAILABLE_CACHED" if row else "MISSING",
            "version": self.version,
            "snapshot": {
                "observed_at": row.observed_at.isoformat(),
                "provider": row.provider,
                "payload": row.payload,
            }
            if row
            else None,
        }


def _truth_counts(case: VeterinaryCase | None) -> tuple[int, int, int]:
    if case is None:
        return 1, 0, 0
    lab = int(case.verified_status == "LAB_CONFIRMED")
    verified = int(case.verified_status in {"VET_VERIFIED", "LAB_CONFIRMED"})
    return 1, verified, lab


def _distance_meters(left: HealthReport, right: HealthReport) -> float:
    if None in {left.latitude, left.longitude, right.latitude, right.longitude}:
        return float("inf")
    assert left.latitude is not None
    assert left.longitude is not None
    assert right.latitude is not None
    assert right.longitude is not None
    left_lat = math.radians(left.latitude)
    right_lat = math.radians(right.latitude)
    delta_lat = right_lat - left_lat
    delta_lon = math.radians(right.longitude - left.longitude)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(left_lat) * math.cos(right_lat) * math.sin(delta_lon / 2) ** 2
    )
    return 6_371_000 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _largest_proximity_cluster(
    rows: list[tuple[HealthReport, VeterinaryCase | None]],
) -> list[tuple[HealthReport, VeterinaryCase | None]]:
    clusters = [
        [
            candidate
            for candidate in rows
            if _distance_meters(anchor[0], candidate[0]) <= PROXIMITY_METERS
        ]
        for anchor in rows
    ]
    return max(clusters, key=len, default=[])


async def refresh_hotspot_candidates(
    session: AsyncSession, *, now: datetime | None = None
) -> list[HotspotCandidate]:
    clock = now or datetime.now(UTC)
    window_start = clock - timedelta(days=WINDOW_DAYS)
    baseline_start = window_start - timedelta(days=BASELINE_DAYS)
    rows = (
        await session.execute(
            select(HealthReport, VeterinaryCase)
            .outerjoin(VeterinaryCase, VeterinaryCase.health_report_id == HealthReport.id)
            .where(
                HealthReport.received_at_server >= baseline_start,
                HealthReport.received_at_server <= clock,
            )
        )
    ).all()
    grouped: dict[str, list[tuple[HealthReport, VeterinaryCase | None]]] = defaultdict(list)
    for report, case in rows:
        grouped[report.village_name].append((report, case))
    produced: list[HotspotCandidate] = []
    for village, village_rows in grouped.items():
        baseline = [
            row
            for row in village_rows
            if baseline_start <= row[0].received_at_server < window_start
        ]
        current_window = [
            row for row in village_rows if window_start <= row[0].received_at_server <= clock
        ]
        current = _largest_proximity_cluster(current_window)
        observed = len(current)
        baseline_rate = len(baseline) / BASELINE_DAYS
        expected = max(1.0, baseline_rate * WINDOW_DAYS)
        lift = observed / expected
        if observed < MINIMUM_CASES or lift < MINIMUM_LIFT:
            continue
        suspected = verified = lab = 0
        for _, case in current:
            row_suspected, row_verified, row_lab = _truth_counts(case)
            suspected += row_suspected
            verified += row_verified
            lab += row_lab
        verification_ratio = verified / observed if observed else 0.0
        confidence = round(
            min(
                0.95,
                0.45
                + min(0.25, 0.05 * (observed - MINIMUM_CASES))
                + 0.1 * min(3.0, lift - 1.0)
                + 0.15 * verification_ratio,
            ),
            6,
        )
        coordinates = [
            (report.latitude, report.longitude)
            for report, _ in current
            if report.latitude is not None and report.longitude is not None
        ]
        latitude = (
            sum(value[0] for value in coordinates) / len(coordinates) if coordinates else None
        )
        longitude = (
            sum(value[1] for value in coordinates) / len(coordinates) if coordinates else None
        )
        area = await session.scalar(
            select(AdministrativeArea).where(
                AdministrativeArea.name == village, AdministrativeArea.level == "VILLAGE"
            )
        )
        raw_key = f"{village}:{clock.date()}:{DETECTOR_VERSION}"
        key = hashlib.sha256(raw_key.encode()).hexdigest()
        candidate = await session.scalar(
            select(HotspotCandidate).where(HotspotCandidate.candidate_key == key)
        )
        if candidate is None:
            candidate = HotspotCandidate(
                candidate_key=key,
                administrative_area_id=area.id if area else None,
                area_name=village,
                area_level="VILLAGE",
                window_start=window_start,
                window_end=clock,
                detector_version=DETECTOR_VERSION,
                status="CANDIDATE",
                baseline_daily_rate=baseline_rate,
                observed_count=observed,
                suspected_count=suspected,
                vet_verified_count=verified,
                lab_confirmed_count=lab,
                confidence=confidence,
                latitude=latitude,
                longitude=longitude,
                centroid=f"SRID=4326;POINT({longitude} {latitude})"
                if latitude is not None and longitude is not None
                else None,
            )
            session.add(candidate)
            await session.flush()
        else:
            candidate.window_start = window_start
            candidate.window_end = clock
            candidate.baseline_daily_rate = baseline_rate
            candidate.observed_count = observed
            candidate.suspected_count = suspected
            candidate.vet_verified_count = verified
            candidate.lab_confirmed_count = lab
            candidate.confidence = confidence
            candidate.latitude = latitude
            candidate.longitude = longitude
            candidate.centroid = (
                f"SRID=4326;POINT({longitude} {latitude})"
                if latitude is not None and longitude is not None
                else None
            )
        await enqueue_alert(
            session,
            deduplication_key=f"hotspot:{candidate.candidate_key}",
            alert_type="HOTSPOT_CANDIDATE",
            administrative_area_id=candidate.administrative_area_id,
            context={
                "candidate_id": str(candidate.id),
                "area_name": village,
                "status": "CANDIDATE_NOT_CONFIRMED_OUTBREAK",
                "observed_count": observed,
                "baseline_daily_rate": round(baseline_rate, 6),
                "confidence": confidence,
                "detector_version": DETECTOR_VERSION,
                "proximity_meters": PROXIMITY_METERS,
                "time_window_days": WINDOW_DAYS,
                "minimum_case_count": MINIMUM_CASES,
                "status_confidence_applied": True,
            },
        )
        produced.append(candidate)
    return produced


async def nearby_case_context(
    session: AsyncSession, report: HealthReport, *, radius_meters: int = 10_000
) -> dict[str, Any]:
    if report.location is None:
        return {"radius_meters": radius_meters, "cases": [], "location_missing": True}
    rows = (
        await session.execute(
            select(
                HealthReport,
                VeterinaryCase,
                func.ST_Distance(HealthReport.location, report.location),
            )
            .outerjoin(VeterinaryCase, VeterinaryCase.health_report_id == HealthReport.id)
            .where(
                HealthReport.id != report.id,
                HealthReport.received_at_server >= report.received_at_server - timedelta(days=7),
                HealthReport.received_at_server <= datetime.now(UTC),
                func.ST_DWithin(HealthReport.location, report.location, radius_meters),
            )
            .order_by(func.ST_Distance(HealthReport.location, report.location))
            .limit(25)
        )
    ).all()
    return {
        "radius_meters": radius_meters,
        "location_missing": False,
        "cases": [
            {
                "report_id": str(other.id),
                "village_name": other.village_name,
                "distance_meters": round(float(distance), 1),
                "suspected_status": case.suspected_status if case else "SUSPECTED",
                "verified_status": case.verified_status if case else "PENDING",
                "lab_status": case.lab_status if case else "NOT_REQUESTED",
            }
            for other, case, distance in rows
        ],
    }


async def surveillance_aggregates(
    session: AsyncSession,
    *,
    level: str,
    date_from: datetime,
    date_to: datetime,
    species: str | None,
    syndrome: str | None,
    status: str | None,
    risk_tier: str | None,
) -> list[dict[str, Any]]:
    query = (
        select(HealthReport, VeterinaryCase, Farm)
        .outerjoin(VeterinaryCase, VeterinaryCase.health_report_id == HealthReport.id)
        .join(Farm, Farm.id == HealthReport.farm_id)
        .where(
            HealthReport.received_at_server >= date_from,
            HealthReport.received_at_server <= date_to,
        )
    )
    if species:
        query = query.where(HealthReport.species == species)
    rows = (await session.execute(query)).all()
    latest_risk: dict[UUID, RiskAssessment] = {}
    assessments = (
        await session.scalars(
            select(RiskAssessment)
            .where(
                RiskAssessment.health_report_id.in_([row[0].id for row in rows] or [UUID(int=0)])
            )
            .order_by(RiskAssessment.created_at)
        )
    ).all()
    for assessment in assessments:
        latest_risk[assessment.health_report_id] = assessment
    areas = (await session.scalars(select(AdministrativeArea))).all()
    area_by_id = {area.id: area for area in areas}
    area_by_name = {(area.name, area.level): area for area in areas}

    def area_for(report: HealthReport, farm: Farm) -> AdministrativeArea | None:
        area = (
            area_by_id.get(farm.administrative_area_id)
            if farm.administrative_area_id is not None
            else None
        ) or area_by_name.get((report.village_name, "VILLAGE"))
        while area is not None and area.level != level:
            area = area_by_id.get(area.parent_id) if area.parent_id is not None else None
        return area

    grouped: dict[str, list[tuple[HealthReport, VeterinaryCase | None, RiskAssessment | None]]] = (
        defaultdict(list)
    )
    for report, case, farm in rows:
        if status and (case.verified_status if case else "PENDING") != status:
            continue
        if syndrome and (case.suspected_label if case else None) != syndrome:
            continue
        report_assessment = latest_risk.get(report.id)
        if (
            risk_tier
            and (report_assessment.urgency_tier if report_assessment else None) != risk_tier
        ):
            continue
        area = area_for(report, farm)
        key = area.name if area else (report.village_name if level == "VILLAGE" else "UNASSIGNED")
        grouped[key].append((report, case, report_assessment))
    output: list[dict[str, Any]] = []
    for area_name, values in sorted(grouped.items()):
        verified = sum(_truth_counts(case)[1] for _, case, _ in values)
        lab = sum(_truth_counts(case)[2] for _, case, _ in values)
        coordinates = [
            (report.latitude, report.longitude)
            for report, _, _ in values
            if report.latitude is not None and report.longitude is not None
        ]
        suppress = len(values) < 2 or not coordinates
        output.append(
            {
                "area_name": area_name,
                "area_level": level,
                "suspected_count": len(values),
                "vet_verified_count": verified,
                "lab_confirmed_count": lab,
                "latitude": None
                if suppress
                else round(sum(item[0] for item in coordinates) / len(coordinates), 3),
                "longitude": None
                if suppress
                else round(sum(item[1] for item in coordinates) / len(coordinates), 3),
                "coordinates_suppressed": suppress,
                "last_updated": max(
                    report.received_at_server for report, _, _ in values
                ).isoformat(),
                "notice": "Aggregated surveillance signal; not a confirmed outbreak",
            }
        )
    return output
