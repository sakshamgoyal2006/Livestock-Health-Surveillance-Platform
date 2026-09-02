from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ErrorBody(APIModel):
    code: str
    message: str
    details: Any | None = None
    request_id: str | None = None


class ErrorEnvelope(APIModel):
    error: ErrorBody


class Page(APIModel):
    items: list[Any]
    page: int
    page_size: int
    total: int


class AuditOut(APIModel):
    id: UUID
    occurred_at: datetime
    actor_user_id: UUID | None
    action: str
    resource_type: str
    resource_id: UUID | None
    request_id: str
    details: dict[str, Any]
    entry_hash: str


MutationResultStatus = Literal["APPLIED", "DUPLICATE", "CONFLICT", "REJECTED"]


class MutationError(APIModel):
    code: str
    message: str


class SyncMutationResult(APIModel):
    client_mutation_id: UUID
    status: MutationResultStatus
    resource_id: UUID | None
    resource_version: int | None
    received_at_server: datetime
    error: MutationError | None = None


class SyncBatchResponse(APIModel):
    results: list[SyncMutationResult]
    server_time: datetime
    next_retry_after_seconds: int | None = Field(default=None, ge=1)
