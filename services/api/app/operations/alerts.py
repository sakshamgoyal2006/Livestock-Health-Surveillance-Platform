from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AlertEvent, NotificationOutbox

DELIVERY_MODE = "DEV_RECORD_ONLY"
RATE_LIMIT_PER_HOUR = 3


class NotificationAdapter(Protocol):
    async def deliver(self, channel: str, recipient: str, payload: dict[str, Any]) -> str: ...


class DevelopmentNoSendAdapter:
    """Records a delivery receipt and never contacts a real recipient."""

    async def deliver(self, channel: str, recipient: str, payload: dict[str, Any]) -> str:
        del channel, recipient, payload
        return f"dev-no-send:{datetime.now(UTC).timestamp()}"


async def enqueue_alert(
    session: AsyncSession,
    *,
    deduplication_key: str,
    alert_type: str,
    context: dict[str, Any],
    health_report_id: UUID | None = None,
    administrative_area_id: UUID | None = None,
    recipient_reference: str = "role:DISTRICT_OFFICER",
    channels: tuple[str, ...] = ("IN_APP",),
    escalation_level: int = 0,
) -> AlertEvent:
    existing = await session.scalar(
        select(AlertEvent).where(AlertEvent.deduplication_key == deduplication_key)
    )
    if existing is not None:
        return existing
    event = AlertEvent(
        health_report_id=health_report_id,
        administrative_area_id=administrative_area_id,
        alert_type=alert_type,
        status="PENDING",
        deduplication_key=deduplication_key,
        context=context,
        escalation_level=escalation_level,
    )
    session.add(event)
    await session.flush()
    for channel in channels:
        session.add(
            NotificationOutbox(
                alert_event_id=event.id,
                channel=channel,
                recipient_reference=recipient_reference,
                payload=context,
                status="PENDING",
                attempt_count=0,
                max_attempts=3,
                delivery_mode=DELIVERY_MODE,
                deduplication_key=f"{deduplication_key}:{channel}:{recipient_reference}",
            )
        )
    return event


async def process_outbox_item(
    session: AsyncSession,
    item: NotificationOutbox,
    *,
    adapter: NotificationAdapter | None = None,
    now: datetime | None = None,
) -> NotificationOutbox:
    clock = now or datetime.now(UTC)
    if item.status in {"DELIVERED_DEV_NO_SEND", "ACKNOWLEDGED", "FAILED_PERMANENT"}:
        return item
    if item.next_attempt_at is not None and item.next_attempt_at > clock:
        return item
    delivered_recently = int(
        await session.scalar(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(
                NotificationOutbox.id != item.id,
                NotificationOutbox.channel == item.channel,
                NotificationOutbox.recipient_reference == item.recipient_reference,
                NotificationOutbox.status == "DELIVERED_DEV_NO_SEND",
                NotificationOutbox.delivered_at >= clock - timedelta(hours=1),
            )
        )
        or 0
    )
    if delivered_recently >= RATE_LIMIT_PER_HOUR:
        item.status = "RATE_LIMITED"
        item.next_attempt_at = clock + timedelta(hours=1)
        item.last_error_code = "RECIPIENT_RATE_LIMIT"
        return item
    item.attempt_count += 1
    simulated_failures = int(item.payload.get("simulate_transient_failures", 0))
    if item.attempt_count <= simulated_failures:
        item.status = (
            "RETRY_PENDING" if item.attempt_count < item.max_attempts else "FAILED_PERMANENT"
        )
        item.last_error_code = "SIMULATED_TRANSIENT_FAILURE"
        item.next_attempt_at = clock + timedelta(seconds=2**item.attempt_count)
        if item.status == "FAILED_PERMANENT" and item.alert_event_id is not None:
            failed_event = await session.get(AlertEvent, item.alert_event_id)
            if failed_event is not None:
                failed_event.status = "ESCALATED_DEVELOPMENT"
                failed_event.escalation_level = min(3, failed_event.escalation_level + 1)
        return item
    receipt = await (adapter or DevelopmentNoSendAdapter()).deliver(
        item.channel, item.recipient_reference, item.payload
    )
    item.status = "DELIVERED_DEV_NO_SEND"
    item.delivery_mode = DELIVERY_MODE
    item.last_error_code = None
    item.next_attempt_at = None
    item.delivered_at = clock
    item.payload = {**item.payload, "development_receipt": receipt, "external_send": False}
    event = await session.get(AlertEvent, item.alert_event_id) if item.alert_event_id else None
    if event is not None and event.status == "PENDING":
        event.status = "DELIVERED_DEV_NO_SEND"
    return item
