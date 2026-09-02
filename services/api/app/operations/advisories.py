from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Advisory, HealthReport


@lru_cache
def advisory_config() -> dict[str, Any]:
    path = Path(__file__).with_name("config") / "advisories.v1.json"
    return cast(dict[str, Any], json.loads(path.read_text("utf-8")))


async def ensure_advisory(
    session: AsyncSession, report: HealthReport, urgency_tier: str
) -> Advisory:
    config = advisory_config()
    language = report.language if report.language in {"en", "mr", "hi"} else "en"
    template_key = f"TRIAGE_{urgency_tier}:{config['version']}"
    existing = await session.scalar(
        select(Advisory).where(
            Advisory.health_report_id == report.id,
            Advisory.language == language,
            Advisory.template_key == template_key,
        )
    )
    if existing is not None:
        return existing
    content = str(config["templates"][urgency_tier][language])
    advisory = Advisory(
        health_report_id=report.id,
        language=language,
        template_key=template_key,
        content=content,
        approved=False,
    )
    session.add(advisory)
    return advisory
