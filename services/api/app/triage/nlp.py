from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal, Protocol, cast

from pydantic import ValidationError

from app.triage.contracts import LanguageCode, SourceSpan, SymptomEntity, SymptomExtraction

NLP_ADAPTER_VERSION = "nlp-lexicon-demo-1.0.0"

LEXICON: dict[str, tuple[str, ...]] = {
    "COUGH": ("cough", "coughing", "खांसी", "खोकला", "khansi", "khokla"),
    "BREATHING_DIFFICULTY": (
        "difficult breathing",
        "breathing difficulty",
        "सांस लेने में कठिनाई",
        "श्वास घेण्यास त्रास",
        "saans lene mein dikkat",
        "shwas ghenyas tras",
    ),
    "NASAL_DISCHARGE": (
        "nasal discharge",
        "runny nose",
        "नाक से पानी",
        "नाकातून पाणी",
        "naak se pani",
        "nakatun pani",
    ),
    "DIARRHEA": ("diarrhea", "loose stool", "दस्त", "जुलाब", "dast", "julab"),
    "SKIN_LESION": ("skin lesion", "rash", "घाव", "त्वचेवर जखम", "ghav", "jakhma"),
    "LAMENESS": ("limping", "lame", "लंगड़ा", "लंगडत", "langda", "langdat"),
    "APPETITE_LOSS": (
        "not eating",
        "no appetite",
        "भूख नहीं",
        "खात नाही",
        "bhukh nahi",
        "khat nahi",
    ),
    "FEVER": ("fever", "high temperature", "बुखार", "ताप", "bukhar", "taap"),
}

NEGATIONS = ("no", "not", "without", "नहीं", "नही", "नाही", "nahi", "nahin")
AMBIGUOUS = ("down", "weak type", "ठीक नहीं", "barobar nahi", "theek nahi")
SEVERE_WORDS = ("severe", "very", "बहुत", "खूप", "bahut", "khup")
MILD_WORDS = ("mild", "slight", "थोड़ा", "थोडा", "thoda")


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    return re.sub(r"\s+", " ", normalized)


def detect_language(text: str, hint: str | None = None) -> LanguageCode:
    if hint in {"en", "mr", "hi"}:
        return cast(LanguageCode, hint)
    if re.search(r"[\u0900-\u097f]", text):
        if any(word in text for word in ("आहे", "नाही", "खोकला", "जुलाब", "खूप")):
            return "mr"
        return "hi"
    if any(word in text for word in ("khokla", "nakatun", "ghenyas", "langdat", "khup")):
        return "mr"
    if any(word in text for word in ("khansi", "saans", "bhukh", "bahut", "bukhar")):
        return "hi"
    if re.search(r"[a-z]", text):
        return "en"
    return "unknown"


def _is_negated(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 24) : min(len(text), end + 12)]
    return any(re.search(rf"(?:^|\s){re.escape(term)}(?:\s|$)", window) for term in NEGATIONS)


def _duration_hours(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(hour|hours|hr|day|days|दिवस|दिन|तास|घंटे)", text)
    if not match:
        return None
    value = float(match.group(1))
    return value * 24 if match.group(2) in {"day", "days", "दिवस", "दिन"} else value


class DeterministicNLPAdapter:
    version = NLP_ADAPTER_VERSION

    def extract(
        self,
        text: str,
        *,
        language_hint: str | None = None,
        source: Literal["FREE_TEXT", "VOICE_TRANSCRIPT", "PROVIDER"] = "FREE_TEXT",
    ) -> SymptomExtraction:
        normalized = normalize_text(text)
        entities: list[SymptomEntity] = []
        negations: list[str] = []
        seen: set[tuple[str, int]] = set()
        for code, phrases in LEXICON.items():
            for phrase in phrases:
                for match in re.finditer(re.escape(phrase), normalized):
                    identity = (code, match.start())
                    if identity in seen:
                        continue
                    seen.add(identity)
                    negated = _is_negated(normalized, match.start(), match.end())
                    if negated:
                        negations.append(code)
                    entities.append(
                        SymptomEntity(
                            code=code,
                            negated=negated,
                            severity="SEVERE"
                            if any(word in normalized for word in SEVERE_WORDS)
                            else "MILD"
                            if any(word in normalized for word in MILD_WORDS)
                            else "UNKNOWN",
                            span=SourceSpan(
                                start=match.start(), end=match.end(), text=match.group(0)
                            ),
                        )
                    )
        ambiguous = [term for term in AMBIGUOUS if term in normalized]
        confidence = min(0.95, 0.45 + 0.1 * len(entities))
        if ambiguous:
            confidence = min(confidence, 0.45)
        return SymptomExtraction(
            detected_language=detect_language(normalized, language_hint),
            normalized_text=normalized,
            symptom_entities=entities,
            negations=sorted(set(negations)),
            duration_hours=_duration_hours(normalized),
            severity="SEVERE"
            if any(word in normalized for word in SEVERE_WORDS)
            else "MILD"
            if any(word in normalized for word in MILD_WORDS)
            else "UNKNOWN",
            body_sites=[],
            ambiguous_terms=ambiguous,
            uncertain=bool(ambiguous) or (bool(normalized) and not entities),
            parser_confidence=confidence if normalized else 0.0,
            adapter_version=self.version,
            source=source,
        )


class SpeechAdapter(Protocol):
    version: str

    def transcribe(self, content: bytes | None, *, transcript: str | None) -> str: ...


class TranscriptEntrySpeechAdapter:
    """Credential-free demo adapter; it never claims acoustic transcription."""

    version = "speech-transcript-entry-demo-1.0.0"

    def transcribe(self, content: bytes | None, *, transcript: str | None) -> str:
        del content
        return normalize_text(transcript or "")


def validate_provider_response(raw: Any) -> SymptomExtraction | None:
    """Treat optional provider output as untrusted and fail closed."""

    try:
        return SymptomExtraction.model_validate(raw)
    except (ValidationError, TypeError, ValueError):
        return None
