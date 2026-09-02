from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from app.triage.contracts import RuleMatch, UrgencyTier


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    operator: Literal["eq", "gte", "lte", "in"]
    value: Any


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    priority: int
    urgency: UrgencyTier
    all: list[Condition] = Field(min_length=1)
    reason_code: str
    message: str


class RuleReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["DEMO_UNVALIDATED", "VETERINARIAN_APPROVED"]
    reviewer: str | None
    reviewed_at: str | None


class RuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_set_id: str
    version: str
    effective_from: str
    provenance: str
    review: RuleReview
    rules: list[Rule]


def _config_path(name: str) -> Path:
    return Path(__file__).with_name("config") / name


@lru_cache
def load_rule_set() -> RuleSet:
    return RuleSet.model_validate_json(_config_path("rules.demo-v1.json").read_text("utf-8"))


@lru_cache
def load_thresholds() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(_config_path("thresholds.demo-v1.json").read_text("utf-8")),
    )


def _matches(value: Any, condition: Condition) -> bool:
    if value is None:
        return False
    if condition.operator == "eq":
        return bool(value == condition.value)
    if condition.operator == "gte":
        return bool(value >= condition.value)
    if condition.operator == "lte":
        return bool(value <= condition.value)
    return bool(value in condition.value)


def evaluate_rules(
    observations: dict[str, Any], rule_set: RuleSet | None = None
) -> list[RuleMatch]:
    selected = rule_set or load_rule_set()
    matches = []
    for rule in sorted(selected.rules, key=lambda item: item.priority, reverse=True):
        if all(_matches(observations.get(condition.field), condition) for condition in rule.all):
            matches.append(
                RuleMatch(
                    rule_id=rule.id,
                    version=selected.version,
                    urgency=rule.urgency,
                    reason_code=rule.reason_code,
                    message=rule.message,
                    validation_status=selected.review.status,
                )
            )
    return matches
