from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    FARMER = "FARMER"
    FIELD_WORKER = "FIELD_WORKER"
    VETERINARIAN = "VETERINARIAN"
    DISTRICT_OFFICER = "DISTRICT_OFFICER"
    ADMIN = "ADMIN"


class Species(StrEnum):
    CATTLE = "CATTLE"
    BUFFALO = "BUFFALO"


class SyncStatus(StrEnum):
    PENDING = "PENDING"
    SYNCED = "SYNCED"
    CONFLICT = "CONFLICT"


class ReportStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    QUEUED_FOR_VET = "QUEUED_FOR_VET"
    CLOSED = "CLOSED"


class MutationType(StrEnum):
    CREATE_REPORT = "CREATE_REPORT"
    UPDATE_REPORT = "UPDATE_REPORT"
