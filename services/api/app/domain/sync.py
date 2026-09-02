from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from geoalchemy2.elements import WKTElement
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import append_audit
from app.domain.access import Actor, can_manage_farm
from app.domain.models import (
    Animal,
    ConsentRecord,
    HealthReport,
    Herd,
    MortalityReport,
    StatusHistory,
    SymptomObservation,
    SyncMutation,
    TriageJob,
)
from app.schemas.common import MutationError, SyncMutationResult
from app.schemas.reports import ReportPayload, ReportUpdate, SyncMutationIn
from app.triage.pipeline import initial_job_values, run_report_triage


class MutationRejected(Exception):
    def __init__(self, code: str, message: str, *, conflict: bool = False) -> None:
        self.code = code
        self.message = message
        self.conflict = conflict
        super().__init__(message)


def _request_hash(mutation: SyncMutationIn) -> str:
    canonical = json.dumps(mutation.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _point(latitude: float | None, longitude: float | None) -> WKTElement | None:
    if latitude is None or longitude is None:
        return None
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)


def _existing_result(existing: SyncMutation, mutation: SyncMutationIn) -> SyncMutationResult:
    if existing.request_hash != _request_hash(mutation):
        return SyncMutationResult(
            client_mutation_id=mutation.client_mutation_id,
            status="CONFLICT",
            resource_id=None,
            resource_version=existing.resource_version,
            received_at_server=datetime.now(UTC),
            error=MutationError(
                code="IDEMPOTENCY_KEY_REUSED",
                message="The mutation identity was previously used with different content",
            ),
        )
    if existing.result_status == "APPLIED":
        status: Literal["DUPLICATE", "CONFLICT", "REJECTED"] = "DUPLICATE"
        error = None
    elif existing.result_status == "CONFLICT":
        status = "CONFLICT"
        error = MutationError(
            code="STALE_VERSION", message="The server resource changed; refresh before retrying"
        )
    else:
        status = "REJECTED"
        error = MutationError(code="PREVIOUSLY_REJECTED", message="This mutation was rejected")
    return SyncMutationResult(
        client_mutation_id=mutation.client_mutation_id,
        status=status,
        resource_id=existing.resource_id,
        resource_version=existing.resource_version,
        received_at_server=existing.received_at_server,
        error=error,
    )


async def _validate_report_ownership(
    session: AsyncSession, actor: Actor, payload: ReportPayload
) -> None:
    if not await can_manage_farm(session, actor, payload.farm_id):
        raise MutationRejected("FARM_ACCESS_DENIED", "Farm is missing or not assigned to this user")
    if payload.animal_id is not None:
        animal = await session.get(Animal, payload.animal_id)
        if animal is None or animal.farm_id != payload.farm_id:
            raise MutationRejected("INVALID_ANIMAL", "Animal does not belong to the selected farm")
        if animal.species != payload.species:
            raise MutationRejected("SPECIES_MISMATCH", "Report species does not match the animal")
    if payload.herd_id is not None:
        herd = await session.get(Herd, payload.herd_id)
        if herd is None or herd.farm_id != payload.farm_id:
            raise MutationRejected("INVALID_HERD", "Herd does not belong to the selected farm")
        if herd.species != payload.species:
            raise MutationRejected("SPECIES_MISMATCH", "Report species does not match the herd")


async def _create_report(
    session: AsyncSession,
    *,
    actor: Actor,
    mutation: SyncMutationIn,
    request_id: str,
) -> tuple[UUID, int]:
    payload = ReportPayload.model_validate(mutation.payload)
    if payload.created_at_device != mutation.created_at_device:
        raise MutationRejected(
            "DEVICE_TIME_MISMATCH", "Mutation and report device timestamps must match"
        )
    await _validate_report_ownership(session, actor, payload)
    if await session.get(HealthReport, payload.id) is not None:
        raise MutationRejected("RESOURCE_ID_EXISTS", "Report ID is already in use", conflict=True)

    report = HealthReport(
        id=payload.id,
        farm_id=payload.farm_id,
        animal_id=payload.animal_id,
        herd_id=payload.herd_id,
        reporter_user_id=actor.id,
        species=payload.species,
        language=payload.language,
        age_band=payload.age_band,
        symptom_onset_at=payload.symptom_onset_at,
        severity=payload.severity,
        appetite=payload.appetite,
        water_intake=payload.water_intake,
        mobility=payload.mobility,
        respiration=payload.respiration,
        visible_lesions=payload.visible_lesions,
        discharge=payload.discharge,
        temperature_c=payload.temperature_c,
        vaccination_status=payload.vaccination_status,
        recent_movement=payload.recent_movement,
        recent_contact=payload.recent_contact,
        mortality_count=payload.mortality_count,
        village_name=payload.village_name,
        location=_point(payload.latitude, payload.longitude),
        latitude=payload.latitude,
        longitude=payload.longitude,
        location_precision=payload.location_precision,
        notes=payload.notes,
        voice_transcript=payload.voice_transcript,
        optional_provider_status=payload.optional_provider_status.model_dump(),
        consent_given=payload.consent_given,
        consent_version=payload.consent_version,
        status="QUEUED_FOR_VET",
        sync_status="SYNCED",
        client_mutation_id=mutation.client_mutation_id,
        idempotency_key=mutation.idempotency_key,
        created_at_device=payload.created_at_device,
        version=1,
    )
    session.add(report)
    # These records are created from scalar foreign keys rather than ORM
    # relationships, so establish the parent row before inserting children.
    await session.flush()
    session.add(TriageJob(**initial_job_values(payload.model_dump(mode="json"))))
    session.add(
        ConsentRecord(
            health_report_id=payload.id,
            user_id=actor.id,
            consent_version=payload.consent_version,
            granted_at_device=payload.created_at_device,
        )
    )
    observations = {
        "severity": payload.severity,
        "appetite": payload.appetite,
        "water_intake": payload.water_intake,
        "mobility": payload.mobility,
        "respiration": payload.respiration,
        "visible_lesions": "UNKNOWN"
        if payload.visible_lesions is None
        else str(payload.visible_lesions),
        "discharge": "UNKNOWN" if payload.discharge is None else str(payload.discharge),
    }
    for code, value in observations.items():
        session.add(
            SymptomObservation(
                health_report_id=payload.id,
                symptom_code=code,
                value=str(value),
                source="GUIDED_FORM",
                observed_at=payload.symptom_onset_at,
            )
        )
    if payload.mortality_count:
        session.add(
            MortalityReport(
                health_report_id=payload.id,
                count=payload.mortality_count,
                observed_at=payload.symptom_onset_at,
            )
        )
    session.add(
        StatusHistory(
            health_report_id=payload.id,
            from_status=None,
            to_status="QUEUED_FOR_VET",
            actor_user_id=actor.id,
            reason="Offline/base report synchronized; veterinary verification required",
        )
    )
    await append_audit(
        session,
        actor_user_id=actor.id,
        action="REPORT_SYNCHRONIZED",
        resource_type="health_report",
        resource_id=payload.id,
        request_id=request_id,
        details={
            "client_mutation_id": str(mutation.client_mutation_id),
            "consent_version": payload.consent_version,
            "location_precision": payload.location_precision,
            "optional_modalities_non_blocking": True,
        },
    )
    return payload.id, 1


async def _update_report(
    session: AsyncSession,
    *,
    actor: Actor,
    mutation: SyncMutationIn,
    request_id: str,
) -> tuple[UUID, int]:
    update = ReportUpdate.model_validate(mutation.payload)
    report = await session.get(HealthReport, update.id)
    if report is None or (report.reporter_user_id != actor.id and actor.role != "ADMIN"):
        raise MutationRejected("REPORT_NOT_FOUND", "Report was not found")
    if report.version != mutation.base_version:
        raise MutationRejected(
            "STALE_VERSION",
            f"Expected version {mutation.base_version}; current version is {report.version}",
            conflict=True,
        )
    if update.severity is not None:
        report.severity = update.severity
    report.notes = update.notes
    report.version += 1
    await append_audit(
        session,
        actor_user_id=actor.id,
        action="REPORT_UPDATED_FROM_SYNC",
        resource_type="health_report",
        resource_id=report.id,
        request_id=request_id,
        details={"base_version": mutation.base_version, "new_version": report.version},
    )
    return report.id, report.version


async def process_mutation(
    session: AsyncSession,
    *,
    actor: Actor,
    mutation: SyncMutationIn,
    request_id: str,
) -> SyncMutationResult:
    # Rollback expires ORM instances. Keep the authenticated identity as an
    # immutable scalar so rejection/audit paths never trigger implicit I/O.
    actor_id = actor.id
    existing = await session.scalar(
        select(SyncMutation).where(
            or_(
                SyncMutation.client_mutation_id == mutation.client_mutation_id,
                SyncMutation.idempotency_key == mutation.idempotency_key,
            )
        )
    )
    if existing is not None:
        if existing.actor_user_id != actor_id:
            return SyncMutationResult(
                client_mutation_id=mutation.client_mutation_id,
                status="CONFLICT",
                resource_id=None,
                resource_version=None,
                received_at_server=datetime.now(UTC),
                error=MutationError(
                    code="MUTATION_IDENTITY_CONFLICT",
                    message="Mutation identity belongs to another user",
                ),
            )
        return _existing_result(existing, mutation)

    request_hash = _request_hash(mutation)
    received = datetime.now(UTC)
    try:
        if mutation.mutation_type == "CREATE_REPORT":
            resource_id, resource_version = await _create_report(
                session, actor=actor, mutation=mutation, request_id=request_id
            )
        else:
            resource_id, resource_version = await _update_report(
                session, actor=actor, mutation=mutation, request_id=request_id
            )
        sync_record = SyncMutation(
            client_mutation_id=mutation.client_mutation_id,
            idempotency_key=mutation.idempotency_key,
            mutation_type=mutation.mutation_type,
            actor_user_id=actor_id,
            resource_type="health_report",
            resource_id=resource_id,
            request_hash=request_hash,
            result_status="APPLIED",
            base_version=mutation.base_version,
            resource_version=resource_version,
            created_at_device=mutation.created_at_device,
            received_at_server=received,
        )
        session.add(sync_record)
        await session.commit()
        # The report transaction is already durable. Optional triage failures are
        # recorded on the retryable job and never turn a successful sync into a loss.
        await run_report_triage(
            session,
            resource_id,
            request_id=request_id,
            actor_user_id=actor_id,
        )
        return SyncMutationResult(
            client_mutation_id=mutation.client_mutation_id,
            status="APPLIED",
            resource_id=resource_id,
            resource_version=resource_version,
            received_at_server=received,
        )
    except (MutationRejected, ValidationError) as exc:
        await session.rollback()
        if isinstance(exc, MutationRejected):
            code, message, conflict = exc.code, exc.message, exc.conflict
        else:
            code, message, conflict = "INVALID_REPORT", "Report fields failed validation", False
        result_status: Literal["CONFLICT", "REJECTED"] = "CONFLICT" if conflict else "REJECTED"
        session.add(
            SyncMutation(
                client_mutation_id=mutation.client_mutation_id,
                idempotency_key=mutation.idempotency_key,
                mutation_type=mutation.mutation_type,
                actor_user_id=actor_id,
                resource_type="health_report",
                resource_id=None,
                request_hash=request_hash,
                result_status=result_status,
                base_version=mutation.base_version,
                resource_version=None,
                created_at_device=mutation.created_at_device,
                received_at_server=received,
            )
        )
        await append_audit(
            session,
            actor_user_id=actor_id,
            action="SYNC_MUTATION_REJECTED",
            resource_type="sync_mutation",
            resource_id=mutation.client_mutation_id,
            request_id=request_id,
            details={"code": code, "conflict": conflict},
        )
        await session.commit()
        return SyncMutationResult(
            client_mutation_id=mutation.client_mutation_id,
            status=result_status,
            resource_id=None,
            resource_version=None,
            received_at_server=received,
            error=MutationError(code=code, message=message),
        )
    except IntegrityError:
        await session.rollback()
        raced = await session.scalar(
            select(SyncMutation).where(
                or_(
                    SyncMutation.client_mutation_id == mutation.client_mutation_id,
                    SyncMutation.idempotency_key == mutation.idempotency_key,
                )
            )
        )
        if raced is not None and raced.actor_user_id == actor_id:
            return _existing_result(raced, mutation)
        return SyncMutationResult(
            client_mutation_id=mutation.client_mutation_id,
            status="CONFLICT",
            resource_id=None,
            resource_version=None,
            received_at_server=received,
            error=MutationError(
                code="CONCURRENT_MUTATION_CONFLICT",
                message="A concurrent request used the same mutation identity",
            ),
        )
