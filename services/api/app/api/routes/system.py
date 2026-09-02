from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.adapters.optional_services import OPTIONAL_ADAPTERS
from app.api.deps import SessionDep

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "api", "time": datetime.now(UTC).isoformat()}


@router.get("/ready")
async def readiness(session: SessionDep) -> dict[str, Any]:
    try:
        postgis_version = await session.scalar(text("SELECT PostGIS_Version()"))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_NOT_READY", "message": "PostGIS is unavailable"},
        ) from exc
    return {
        "status": "ready",
        "database": "postgresql",
        "postgis": postgis_version,
        "optional_components": {
            name: adapter.status().__dict__ for name, adapter in OPTIONAL_ADAPTERS.items()
        },
    }
