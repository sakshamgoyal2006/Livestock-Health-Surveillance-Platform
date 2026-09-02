from __future__ import annotations

import math
from uuid import UUID

from app.triage.contracts import (
    ExplanationContribution,
    FeatureSnapshotContract,
    RuleMatch,
    TriageDecision,
    UrgencyTier,
)
from app.triage.rules import load_rule_set, load_thresholds

RISK_MODEL_VERSION = "interpretable-risk-demo-1.0.0"
PIPELINE_VERSION = "triage-pipeline-1.0.0"
SUPPORTED_FEATURE_SCHEMA_VERSION = "triage-features-v1.0.0"


def _softmax(scores: list[float]) -> list[float]:
    shifted = [math.exp(value - max(scores)) for value in scores]
    total = sum(shifted)
    return [value / total for value in shifted]


def _contribution(
    feature: str,
    value: float | int | str | bool | None,
    amount: float,
    message: str,
) -> ExplanationContribution:
    return ExplanationContribution(
        feature=feature,
        value=value,
        contribution=amount,
        direction="HIGHER" if amount > 0 else "LOWER" if amount < 0 else "NEUTRAL",
        message=message,
    )


def score_interpretable_baseline(
    report_id: UUID,
    features: FeatureSnapshotContract,
    rule_matches: list[RuleMatch],
    *,
    model_available: bool = True,
) -> TriageDecision:
    if features.feature_schema_version != SUPPORTED_FEATURE_SCHEMA_VERSION:
        raise ValueError("INCOMPATIBLE_FEATURE_SCHEMA_VERSION")
    values = features.values
    missing = features.missingness
    contributions: list[ExplanationContribution] = []
    vet_score = 0.0
    emergency_score = -1.0

    severity = values["guided_severity"]
    if severity == "SEVERE":
        emergency_score += 1.15
        vet_score += 0.5
        contributions.append(
            _contribution(
                "guided_severity", severity, 1.15, "Severe guided severity increased urgency"
            )
        )
    elif severity == "MODERATE":
        vet_score += 0.8
        contributions.append(
            _contribution(
                "guided_severity", severity, 0.8, "Moderate guided severity increased review need"
            )
        )
    if values["guided_respiration"] in {"DIFFICULT", "RAPID"}:
        emergency_score += 0.9
        contributions.append(
            _contribution(
                "guided_respiration",
                values["guided_respiration"],
                0.9,
                "Reported breathing signs increased urgency",
            )
        )
    if values["guided_mobility"] == "UNABLE_TO_STAND":
        emergency_score += 1.1
        contributions.append(
            _contribution(
                "guided_mobility", "UNABLE_TO_STAND", 1.1, "Unable to stand increased urgency"
            )
        )
    mortality = int(values["guided_mortality_count"] or 0)
    if mortality > 0:
        emergency_score += min(1.5, 0.8 + 0.1 * mortality)
        contributions.append(
            _contribution(
                "guided_mortality_count", mortality, 0.9, "Reported mortality increased urgency"
            )
        )
    if values["guided_appetite"] in {"REDUCED", "NONE"}:
        vet_score += 0.45
    if values["guided_vaccination_status"] in {"OVERDUE", "UNKNOWN"}:
        vet_score += 0.2
    if values["guided_nlp_conflict_count"]:
        vet_score += 0.45
        contributions.append(
            _contribution(
                "guided_nlp_conflict_count",
                values["guided_nlp_conflict_count"],
                0.45,
                "Text and guided answers conflict; guided answers remain primary",
            )
        )
    if values["vision_uncertainty"] is not None:
        vet_score += float(values["vision_uncertainty"] or 0) * 0.35

    missing_count = sum(missing.values())
    insufficient = missing_count >= 6 or bool(values["guided_nlp_conflict_count"])
    if insufficient:
        vet_score += 0.65
        contributions.append(
            _contribution(
                "missing_modality_count",
                missing_count,
                0.65,
                "Missing or conflicting information favors veterinary review, not low risk",
            )
        )

    probabilities_raw = _softmax([0.4, vet_score, emergency_score]) if model_available else None
    probabilities: dict[UrgencyTier, float] = (
        {
            "LOW": round(probabilities_raw[0], 8),
            "VET_REVIEW": round(probabilities_raw[1], 8),
            "EMERGENCY": round(probabilities_raw[2], 8),
        }
        if probabilities_raw
        else {"LOW": 0.0, "VET_REVIEW": 1.0, "EMERGENCY": 0.0}
    )
    thresholds = load_thresholds()
    emergency_override = next(
        (match for match in rule_matches if match.urgency == "EMERGENCY"), None
    )
    if emergency_override:
        urgency: UrgencyTier = "EMERGENCY"
        override = True
        policy = "EMERGENCY_RULE_OVERRIDE"
    elif not model_available:
        urgency = "VET_REVIEW"
        override = False
        policy = "MODEL_UNAVAILABLE_SAFE_BASELINE"
    elif probabilities["EMERGENCY"] > thresholds["emergency_probability"]:
        urgency = "EMERGENCY"
        override = False
        policy = "DEMO_PROBABILITY_THRESHOLD"
    elif insufficient or probabilities["VET_REVIEW"] >= thresholds["vet_review_probability"]:
        urgency = "VET_REVIEW"
        override = False
        policy = "REVIEW_THRESHOLD_OR_INSUFFICIENT_INFORMATION"
    else:
        urgency = "LOW"
        override = False
        policy = "DEMO_LOW_TIER"

    conditions = {
        "RESPIRATORY_SYNDROME": 0.72
        if values["guided_respiration"] in {"DIFFICULT", "RAPID"}
        else 0.12,
        "MOBILITY_CONCERN": 0.78
        if values["guided_mobility"] in {"LIMPING", "UNABLE_TO_STAND"}
        else 0.08,
        "SYSTEMIC_ILLNESS_PATTERN": 0.66 if severity in {"MODERATE", "SEVERE"} else 0.18,
        "VISIBLE_CONDITION_PATTERN": float(
            values.get("vision_probability_skin_lesion")
            or values.get("guided_visible_lesions")
            or 0.0
        ),
        "OTHER_UNKNOWN": float(values.get("vision_other_unknown_probability") or 0.0),
    }
    uncertainty_values = [
        float(values["vision_uncertainty"]) if values["vision_uncertainty"] is not None else 0.65,
        1.0 - float(values["nlp_confidence"]) if values["nlp_confidence"] is not None else 0.6,
        min(1.0, missing_count / max(1, len(missing))),
    ]
    uncertainty = round(sum(uncertainty_values) / len(uncertainty_values), 6)
    return TriageDecision(
        report_id=report_id,
        urgency_tier=urgency,
        urgency_probabilities=probabilities,
        suspected_condition_likelihoods=conditions,
        rule_matches=rule_matches,
        override_applied=override,
        uncertainty=uncertainty,
        insufficient_information=insufficient,
        model_version=RISK_MODEL_VERSION if model_available else None,
        rule_version=load_rule_set().version,
        threshold_version=str(thresholds["version"]),
        feature_schema_version=features.feature_schema_version,
        calibration_status="DEMO_UNVALIDATED" if model_available else "MODEL_UNAVAILABLE",
        modality_status={
            "guided_form": "PRIMARY",
            "nlp": "MISSING" if missing["nlp_missing"] else "AVAILABLE_SECONDARY",
            "vision": "MISSING" if missing["vision_missing"] else "AVAILABLE_SECONDARY",
            "weather": "MISSING" if missing["weather_missing"] else "AVAILABLE_CONTEXT",
            "history": "MISSING" if missing["history_missing"] else "AVAILABLE_CONTEXT",
            "gis": "MISSING" if missing["gis_context_missing"] else "AVAILABLE_CONTEXT",
        },
        contributions=sorted(contributions, key=lambda item: abs(item.contribution), reverse=True)[
            :5
        ],
        decision_trace=[
            {"step": 1, "component": "rules", "matches": len(rule_matches)},
            {
                "step": 2,
                "component": "interpretable_demo_model",
                "available": model_available,
                "calibration": "DEMO_UNVALIDATED",
            },
            {"step": 3, "component": "decision_policy", "policy": policy},
        ],
    )
