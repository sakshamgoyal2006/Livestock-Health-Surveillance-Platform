from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.triage.contracts import FeatureSnapshotContract, SymptomExtraction, VisionPrediction

FEATURE_SCHEMA_VERSION = "triage-features-v1.0.0"
LEAKAGE_EXCLUSIONS = [
    "vet_review",
    "verified_label",
    "lab_result",
    "future_outcome",
    "post_triage_action",
]


class ContextFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prior_condition_count: int | None = None
    vaccination_record_count: int | None = None
    weather_temperature_c: float | None = None
    weather_humidity_pct: float | None = None
    nearby_recent_suspected_count: int | None = None


def _guided_conflicts(report: Any, nlp: SymptomExtraction | None) -> list[str]:
    if nlp is None:
        return []
    positive = {entity.code for entity in nlp.symptom_entities if not entity.negated}
    conflicts = []
    if report.respiration == "NORMAL" and "BREATHING_DIFFICULTY" in positive:
        conflicts.append("respiration")
    if report.appetite == "NORMAL" and "APPETITE_LOSS" in positive:
        conflicts.append("appetite")
    if report.visible_lesions is False and "SKIN_LESION" in positive:
        conflicts.append("visible_lesions")
    return conflicts


def build_features(
    report: Any,
    *,
    nlp: SymptomExtraction | None,
    vision: VisionPrediction | None,
    context: ContextFeatures,
) -> FeatureSnapshotContract:
    nlp_positive = (
        sorted({entity.code for entity in nlp.symptom_entities if not entity.negated})
        if nlp
        else None
    )
    values: dict[str, float | int | str | bool | None] = {
        "guided_severity": report.severity,
        "guided_appetite": report.appetite,
        "guided_water_intake": report.water_intake,
        "guided_mobility": report.mobility,
        "guided_respiration": report.respiration,
        "guided_visible_lesions": report.visible_lesions,
        "guided_discharge": report.discharge,
        "guided_temperature_c": report.temperature_c,
        "guided_mortality_count": report.mortality_count,
        "guided_vaccination_status": report.vaccination_status,
        "guided_recent_movement": report.recent_movement,
        "guided_recent_contact": report.recent_contact,
        "location_precision": report.location_precision,
        "nlp_entity_count": len(nlp_positive) if nlp_positive is not None else None,
        "nlp_confidence": nlp.parser_confidence if nlp else None,
        "nlp_uncertain": nlp.uncertain if nlp else None,
        "guided_nlp_conflict_count": len(_guided_conflicts(report, nlp)) if nlp else None,
        "vision_quality": vision.quality.score if vision else None,
        "vision_uncertainty": vision.uncertainty if vision else None,
        "vision_other_unknown_probability": vision.probabilities[-1] if vision else None,
        "prior_condition_count": context.prior_condition_count,
        "vaccination_record_count": context.vaccination_record_count,
        "weather_temperature_c": context.weather_temperature_c,
        "weather_humidity_pct": context.weather_humidity_pct,
        "nearby_recent_suspected_count": context.nearby_recent_suspected_count,
    }
    if vision:
        values.update(
            {
                f"vision_probability_{code.lower()}": probability
                for code, probability in zip(vision.class_order, vision.probabilities, strict=True)
            }
        )
    missingness = {
        "nlp_missing": nlp is None,
        "vision_missing": vision is None,
        "weather_missing": context.weather_temperature_c is None,
        "history_missing": context.prior_condition_count is None,
        "vaccination_history_missing": context.vaccination_record_count is None,
        "gis_context_missing": context.nearby_recent_suspected_count is None,
        "temperature_missing": report.temperature_c is None,
        "recent_movement_missing": report.recent_movement is None,
        "recent_contact_missing": report.recent_contact is None,
    }
    return FeatureSnapshotContract(
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        values=values,
        missingness=missingness,
        source_versions={
            "nlp": nlp.adapter_version if nlp else None,
            "vision": vision.model_version if vision else None,
            "weather": "database-weather-context-v1"
            if context.weather_temperature_c is not None
            else None,
            "gis": "postgis-nearby-context-v1"
            if context.nearby_recent_suspected_count is not None
            else None,
        },
        built_at=datetime.now(UTC),
        leakage_guard=LEAKAGE_EXCLUSIONS,
    )
