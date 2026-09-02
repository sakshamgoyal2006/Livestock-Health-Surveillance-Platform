"""Add Checkpoint 3 operational workflow and governance fields.

Revision ID: 0003_checkpoint_3
Revises: 0002_checkpoint_2
Create Date: 2026-09-02
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.db.base import Base
from app.domain import models  # noqa: F401

revision = "0003_checkpoint_3"
down_revision = "0002_checkpoint_2"
branch_labels = None
depends_on = None


def _column_names(table: str) -> set[str]:
    return {str(item["name"]) for item in sa.inspect(op.get_bind()).get_columns(table)}


def _add_missing(table: str, column: sa.Column[object]) -> bool:
    if str(column.name) in _column_names(table):
        return False
    op.add_column(table, column)
    return True


def upgrade() -> None:
    # Earlier migrations intentionally use current metadata for clean installs. Calling
    # create_all first therefore creates new tables, while the guarded ALTERs below
    # safely upgrade a database that was last migrated with Checkpoint 2 code.
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)
    _add_missing(
        "alert_events",
        sa.Column("administrative_area_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    _add_missing(
        "alert_events",
        sa.Column(
            "context", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
    )
    _add_missing(
        "alert_events",
        sa.Column("escalation_level", sa.Integer(), nullable=False, server_default="0"),
    )
    _add_missing(
        "alert_events",
        sa.Column("acknowledged_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    _add_missing("alert_events", sa.Column("acknowledged_at", sa.DateTime(timezone=True)))
    foreign_keys = {
        item.get("name") for item in sa.inspect(op.get_bind()).get_foreign_keys("alert_events")
    }
    if (
        "fk_alert_area" not in foreign_keys
        and "fk_alert_events_administrative_area_id_administrative_areas" not in foreign_keys
    ):
        op.create_foreign_key(
            "fk_alert_area",
            "alert_events",
            "administrative_areas",
            ["administrative_area_id"],
            ["id"],
        )
    if (
        "fk_alert_ack_user" not in foreign_keys
        and "fk_alert_events_acknowledged_by_user_id_users" not in foreign_keys
    ):
        op.create_foreign_key(
            "fk_alert_ack_user",
            "alert_events",
            "users",
            ["acknowledged_by_user_id"],
            ["id"],
        )
    index_names = {
        item.get("name") for item in sa.inspect(op.get_bind()).get_indexes("alert_events")
    }
    if "ix_alert_events_administrative_area_id" not in index_names:
        op.create_index(
            "ix_alert_events_administrative_area_id", "alert_events", ["administrative_area_id"]
        )

    for column in (
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(80)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("delivery_mode", sa.String(32), nullable=False, server_default="DEV_RECORD_ONLY"),
        sa.Column("deduplication_key", sa.String(220)),
    ):
        _add_missing("notification_outbox", column)
    outbox_uniques = {
        item.get("name")
        for item in sa.inspect(op.get_bind()).get_unique_constraints("notification_outbox")
    }
    if "uq_notification_outbox_deduplication_key" not in outbox_uniques:
        op.create_unique_constraint(
            "uq_notification_outbox_deduplication_key",
            "notification_outbox",
            ["deduplication_key"],
        )

    _add_missing(
        "dataset_versions",
        sa.Column("status", sa.String(32), nullable=False, server_default="LOCKED"),
    )
    _add_missing(
        "dataset_versions", sa.Column("row_count", sa.Integer(), nullable=False, server_default="0")
    )
    _add_missing("dataset_versions", sa.Column("feature_schema_version", sa.String(40)))
    _add_missing("dataset_versions", sa.Column("locked_benchmark_checksum", sa.String(64)))

    _add_missing(
        "retraining_candidates",
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    _add_missing(
        "retraining_candidates",
        sa.Column(
            "provenance",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    _add_missing(
        "retraining_candidates",
        sa.Column("quality_review_status", sa.String(32), nullable=False, server_default="PENDING"),
    )
    _add_missing(
        "retraining_candidates", sa.Column("deduplication_hash", sa.String(64), nullable=False)
    )
    _add_missing(
        "retraining_candidates", sa.Column("immutable_checksum", sa.String(64), nullable=False)
    )
    candidate_uniques = {
        item.get("name")
        for item in sa.inspect(op.get_bind()).get_unique_constraints("retraining_candidates")
    }
    if (
        "uq_retraining_candidates_deduplication_hash" not in candidate_uniques
        and "uq_retraining_candidate_deduplication_hash" not in candidate_uniques
    ):
        op.create_unique_constraint(
            "uq_retraining_candidate_deduplication_hash",
            "retraining_candidates",
            ["deduplication_hash"],
        )


def downgrade() -> None:
    op.drop_table("hotspot_candidates")
    op.drop_table("case_follow_ups")
    op.drop_table("veterinary_cases")
    op.drop_constraint(
        "uq_retraining_candidate_deduplication_hash", "retraining_candidates", type_="unique"
    )
    for name in (
        "immutable_checksum",
        "deduplication_hash",
        "quality_review_status",
        "provenance",
        "source_record_id",
    ):
        op.drop_column("retraining_candidates", name)
    for name in ("locked_benchmark_checksum", "feature_schema_version", "row_count", "status"):
        op.drop_column("dataset_versions", name)
    op.drop_constraint(
        "uq_notification_outbox_deduplication_key", "notification_outbox", type_="unique"
    )
    for name in (
        "deduplication_key",
        "delivery_mode",
        "delivered_at",
        "last_error_code",
        "next_attempt_at",
        "max_attempts",
    ):
        op.drop_column("notification_outbox", name)
    op.drop_index("ix_alert_events_administrative_area_id", table_name="alert_events")
    op.drop_constraint("fk_alert_ack_user", "alert_events", type_="foreignkey")
    op.drop_constraint("fk_alert_area", "alert_events", type_="foreignkey")
    for name in (
        "acknowledged_at",
        "acknowledged_by_user_id",
        "escalation_level",
        "context",
        "administrative_area_id",
    ):
        op.drop_column("alert_events", name)
