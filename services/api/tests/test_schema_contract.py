from __future__ import annotations

import os
from pathlib import Path

import yaml
from geoalchemy2 import Geography

from app.db.base import Base
from app.domain import models  # noqa: F401


def test_required_domain_tables_are_in_migration_metadata() -> None:
    expected = {
        "users",
        "farmer_profiles",
        "field_worker_profiles",
        "veterinarian_profiles",
        "farms",
        "herds",
        "animals",
        "ownership_assignments",
        "health_reports",
        "mortality_reports",
        "symptom_observations",
        "media_assets",
        "vaccination_records",
        "treatment_records",
        "disease_history",
        "risk_assessments",
        "feature_snapshots",
        "explanations",
        "model_versions",
        "vet_reviews",
        "case_assignments",
        "status_history",
        "lab_referrals",
        "lab_results",
        "advisories",
        "alert_events",
        "notification_outbox",
        "administrative_areas",
        "weather_snapshots",
        "surveillance_aggregates",
        "retraining_candidates",
        "dataset_versions",
        "promotion_approvals",
        "sync_mutations",
        "audit_logs",
        "consent_records",
        "retention_requests",
    }
    assert expected <= set(Base.metadata.tables)


def test_report_and_farm_locations_are_postgis_geography_with_gist_indexes() -> None:
    for table_name in ("farms", "health_reports"):
        table = Base.metadata.tables[table_name]
        location = table.c.location.type
        assert isinstance(location, Geography)
        assert location.srid == 4326
        assert any(
            index.dialect_options["postgresql"].get("using") == "gist" for index in table.indexes
        )


def test_offline_identity_and_audit_fields_are_typed_columns() -> None:
    report = Base.metadata.tables["health_reports"]
    for name in (
        "created_at_device",
        "received_at_server",
        "updated_at",
        "sync_status",
        "client_mutation_id",
        "idempotency_key",
        "version",
        "consent_given",
        "consent_version",
    ):
        assert name in report.c
    assert report.c.client_mutation_id.unique
    assert report.c.idempotency_key.unique


def test_compose_declares_postgis_api_and_web_health_dependencies() -> None:
    configured_path = os.environ.get("COMPOSE_FILE_UNDER_TEST")
    if configured_path:
        compose_path = Path(configured_path)
    else:
        compose_path = next(
            candidate
            for parent in Path(__file__).resolve().parents
            if (candidate := parent / "docker-compose.yml").exists()
        )
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    assert set(compose["services"]) == {"db", "api", "web"}
    assert compose["services"]["db"]["image"].startswith("postgis/postgis:")
    assert compose["services"]["api"]["depends_on"]["db"]["condition"] == "service_healthy"
    assert compose["services"]["web"]["depends_on"]["api"]["condition"] == "service_healthy"
