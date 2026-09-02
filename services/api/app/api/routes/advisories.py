from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import SessionDep, require_roles
from app.domain.models import Advisory, HealthReport, User

router = APIRouter(prefix="/api/v1/advisories", tags=["multilingual advisories"])
AdvisoryReader = Annotated[
    User,
    Depends(require_roles("FARMER", "FIELD_WORKER", "VETERINARIAN", "ADMIN")),
]


@router.get("")
async def list_advisories(session: SessionDep, actor: AdvisoryReader) -> list[dict[str, Any]]:
    query = select(Advisory, HealthReport).join(
        HealthReport, HealthReport.id == Advisory.health_report_id
    )
    if actor.role in {"FARMER", "FIELD_WORKER"}:
        query = query.where(HealthReport.reporter_user_id == actor.id)
    rows = (await session.execute(query.order_by(Advisory.created_at.desc()))).all()
    return [
        {
            "id": advisory.id,
            "report_id": report.id,
            "language": advisory.language,
            "template_key": advisory.template_key,
            "content": advisory.content,
            "review_status": "DEMO_TEMPLATE_NOT_CLINICALLY_VALIDATED"
            if not advisory.approved
            else "APPROVED_TEMPLATE",
        }
        for advisory, report in rows
    ]
