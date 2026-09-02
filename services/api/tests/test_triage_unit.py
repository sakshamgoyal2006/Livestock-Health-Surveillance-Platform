from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image
from pydantic import ValidationError

from app.triage.contracts import VISIBLE_CLASS_ORDER, ImageQuality, VisionPrediction
from app.triage.features import FEATURE_SCHEMA_VERSION, ContextFeatures, build_features
from app.triage.nlp import (
    DeterministicNLPAdapter,
    TranscriptEntrySpeechAdapter,
    validate_provider_response,
)
from app.triage.risk import RISK_MODEL_VERSION, score_interpretable_baseline
from app.triage.rules import evaluate_rules
from app.triage.vision import (
    DeterministicVisionAdapter,
    ImageRejected,
    UnavailableVisionAdapter,
    assess_quality,
    sanitize_image,
)


def report(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": uuid4(),
        "severity": "MILD",
        "appetite": "NORMAL",
        "water_intake": "NORMAL",
        "mobility": "NORMAL",
        "respiration": "NORMAL",
        "visible_lesions": None,
        "discharge": None,
        "temperature_c": None,
        "mortality_count": 0,
        "vaccination_status": "UNKNOWN",
        "recent_movement": None,
        "recent_contact": None,
        "location_precision": "VILLAGE_ONLY",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def image_bytes(kind: str = "checker", size: int = 256) -> bytes:
    image = Image.new("RGB", (size, size))
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            if kind == "checker":
                value = 40 if (x // 8 + y // 8) % 2 else 210
                pixels[x, y] = (value, 160, 255 - value)
            elif kind == "dark":
                pixels[x, y] = (2, 2, 2)
            else:
                pixels[x, y] = (128, 128, 128)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@pytest.mark.parametrize(
    ("observations", "expected"),
    [
        ({"mortality_count": 1}, "DEMO_MORTALITY_PRESENT"),
        ({"mortality_count": 0}, None),
        ({"mobility": "UNABLE_TO_STAND"}, "DEMO_UNABLE_TO_STAND"),
        (
            {"severity": "SEVERE", "respiration": "DIFFICULT"},
            "DEMO_SEVERE_BREATHING",
        ),
        ({"severity": "MODERATE", "respiration": "DIFFICULT"}, None),
        ({"temperature_c": 40.5}, "DEMO_HIGH_TEMPERATURE"),
        ({"temperature_c": 40.499}, None),
        ({"appetite": "NONE", "water_intake": "NONE"}, "DEMO_NO_INTAKE"),
        ({"appetite": "NONE", "water_intake": None}, None),
    ],
)
def test_rule_boundaries(observations: dict[str, object], expected: str | None) -> None:
    matches = evaluate_rules(observations)
    assert (matches[0].rule_id if matches else None) == expected
    assert all(match.validation_status == "DEMO_UNVALIDATED" for match in matches)


def test_emergency_rule_precedence_is_stable() -> None:
    matches = evaluate_rules(
        {
            "mortality_count": 1,
            "mobility": "UNABLE_TO_STAND",
            "severity": "SEVERE",
            "respiration": "DIFFICULT",
            "temperature_c": 41.0,
        }
    )
    assert [match.urgency for match in matches[:3]] == ["EMERGENCY"] * 3
    assert matches[0].rule_id == "DEMO_MORTALITY_PRESENT"


@pytest.mark.parametrize(
    ("text", "hint", "language", "code", "negated"),
    [
        ("severe cough for 2 days", "en", "en", "COUGH", False),
        ("खूप खोकला 2 दिवस", "mr", "mr", "COUGH", False),
        ("बहुत खांसी 3 दिन", "hi", "hi", "COUGH", False),
        ("khokla ani nakatun pani", None, "mr", "NASAL_DISCHARGE", False),
        ("khansi nahi", "hi", "hi", "COUGH", True),
        ("no cough but mild fever", "en", "en", "COUGH", True),
    ],
)
def test_multilingual_nlp_fixtures(
    text: str, hint: str | None, language: str, code: str, negated: bool
) -> None:
    result = DeterministicNLPAdapter().extract(text, language_hint=hint)
    assert result.detected_language == language
    entity = next(item for item in result.symptom_entities if item.code == code)
    assert entity.negated is negated
    assert result.adapter_version.startswith("nlp-lexicon-demo")


def test_nlp_ambiguity_speech_and_malformed_provider_are_safe() -> None:
    ambiguous = DeterministicNLPAdapter().extract("animal is down and theek nahi")
    assert ambiguous.uncertain is True
    assert ambiguous.parser_confidence <= 0.45
    assert TranscriptEntrySpeechAdapter().transcribe(None, transcript="  KHOKLA  ") == "khokla"
    assert validate_provider_response({"detected_language": "en", "unexpected": True}) is None


def test_image_security_quality_class_order_and_unknown_behavior() -> None:
    clean = sanitize_image(image_bytes(), "image/png")
    quality = assess_quality(clean)
    assert quality.accepted is True
    prediction = DeterministicVisionAdapter().predict(clean)
    assert prediction.class_order == VISIBLE_CLASS_ORDER
    assert sum(prediction.probabilities) == pytest.approx(1.0)
    assert prediction.probabilities[-1] >= 0.2
    assert prediction.calibration_status == "DEMO_UNVALIDATED"
    with pytest.raises(ImageRejected):
        sanitize_image(b"not an image", "image/png")
    with pytest.raises(ImageRejected) as unsupported:
        sanitize_image(image_bytes(), "application/octet-stream")
    assert unsupported.value.code == "UNSUPPORTED_MEDIA"
    with pytest.raises(ImageRejected) as too_large:
        sanitize_image(b"x" * (10 * 1024 * 1024 + 1), "image/png")
    assert too_large.value.code == "INVALID_IMAGE_SIZE"


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (image_bytes("flat"), "IMAGE_TOO_BLURRY"),
        (image_bytes("dark"), "IMAGE_UNDEREXPOSED"),
        (image_bytes(size=64), "RESOLUTION_TOO_LOW"),
    ],
)
def test_image_quality_rejections(content: bytes, reason: str) -> None:
    quality = assess_quality(content)
    assert quality.accepted is False
    assert reason in quality.rejection_reasons
    with pytest.raises(ImageRejected) as error:
        DeterministicVisionAdapter().predict(content)
    assert error.value.code == "IMAGE_QUALITY_REJECTED"


def test_vision_contract_and_outage_fail_closed() -> None:
    with pytest.raises(ValidationError):
        VisionPrediction(
            class_order=list(reversed(VISIBLE_CLASS_ORDER)),
            probabilities=[0.2] * 5,
            quality=ImageQuality(
                accepted=True,
                score=1,
                width=256,
                height=256,
                blur_score=1,
                exposure_score=1,
                rejection_reasons=[],
            ),
            uncertainty=0.2,
            uncertain=False,
            model_version="incompatible",
            calibration_status="DEMO_UNVALIDATED",
        )
    with pytest.raises(RuntimeError, match="VISION_MODEL_UNAVAILABLE"):
        UnavailableVisionAdapter().predict(image_bytes())


@pytest.mark.parametrize(
    ("nlp_present", "vision_present", "weather_present", "history", "missing_key"),
    [
        (False, False, False, None, "nlp_missing"),
        (True, False, False, None, "vision_missing"),
        (False, True, False, None, "weather_missing"),
        (False, False, False, 1, "weather_missing"),
    ],
)
def test_feature_builder_preserves_missing_modalities(
    nlp_present: bool,
    vision_present: bool,
    weather_present: bool,
    history: int | None,
    missing_key: str,
) -> None:
    nlp = DeterministicNLPAdapter().extract("cough") if nlp_present else None
    vision = DeterministicVisionAdapter().predict(image_bytes()) if vision_present else None
    snapshot = build_features(
        report(),
        nlp=nlp,
        vision=vision,
        context=ContextFeatures(
            prior_condition_count=history,
            vaccination_record_count=0 if history is not None else None,
            weather_temperature_c=31.0 if weather_present else None,
            weather_humidity_pct=65.0 if weather_present else None,
            nearby_recent_suspected_count=None,
        ),
    )
    assert snapshot.feature_schema_version == FEATURE_SCHEMA_VERSION
    assert snapshot.missingness[missing_key] is True
    if not vision_present:
        assert snapshot.values["vision_quality"] is None
    if not weather_present:
        assert snapshot.values["weather_temperature_c"] is None
    assert "vet_review" in snapshot.leakage_guard


def test_guided_form_is_primary_rule_override_and_model_outage_routes_review() -> None:
    nlp = DeterministicNLPAdapter().extract("difficult breathing")
    features = build_features(
        report(respiration="NORMAL", mortality_count=1),
        nlp=nlp,
        vision=None,
        context=ContextFeatures(),
    )
    assert features.values["guided_respiration"] == "NORMAL"
    assert features.values["guided_nlp_conflict_count"] == 1
    rules = evaluate_rules({"mortality_count": 1})
    decision = score_interpretable_baseline(uuid4(), features, rules)
    assert decision.urgency_tier == "EMERGENCY"
    assert decision.override_applied is True
    unavailable = score_interpretable_baseline(uuid4(), features, [], model_available=False)
    assert unavailable.urgency_tier == "VET_REVIEW"
    assert unavailable.calibration_status == "MODEL_UNAVAILABLE"
    assert decision.model_version == RISK_MODEL_VERSION
    incompatible = features.model_copy(update={"feature_schema_version": "future-v99"})
    with pytest.raises(ValueError, match="INCOMPATIBLE_FEATURE_SCHEMA_VERSION"):
        score_interpretable_baseline(uuid4(), incompatible, [])
