from __future__ import annotations

import asyncio

from app.operations.advisories import advisory_config
from app.operations.alerts import DevelopmentNoSendAdapter
from app.operations.cases import CASE_TRANSITIONS
from app.operations.mlops import _evaluate, locked_benchmark


def test_case_state_machine_has_guarded_terminal_and_lab_branches() -> None:
    assert CASE_TRANSITIONS["TRIAGED"] == {"ASSIGNED"}
    assert "VET_VERIFIED" in CASE_TRANSITIONS["UNDER_REVIEW"]
    assert "SAMPLE_REQUESTED" in CASE_TRANSITIONS["UNDER_REVIEW"]
    assert {"LAB_CONFIRMED", "LAB_NEGATIVE", "INCONCLUSIVE"}.issubset(
        CASE_TRANSITIONS["LAB_PENDING"]
    )
    assert CASE_TRANSITIONS["CLOSED"] == set()


def test_advisory_contract_has_all_languages_and_demo_review_status() -> None:
    config = advisory_config()
    assert config["review_status"] == "DEMO_UNVALIDATED"
    for tier in ("LOW", "VET_REVIEW", "EMERGENCY"):
        assert set(config["templates"][tier]) == {"en", "mr", "hi"}
        assert all(config["templates"][tier].values())


def test_locked_benchmark_is_synthetic_and_regression_fixture_is_rejected_by_metrics() -> None:
    benchmark = locked_benchmark()
    assert benchmark["provenance"] == "SYNTHETIC_DEMO"
    baseline = _evaluate("BASELINE_EQUIVALENT")
    regression = _evaluate("INTENTIONAL_REGRESSION_FIXTURE")
    assert baseline["calibration_status"] == "DEMO_UNVALIDATED"
    assert regression["emergency_sensitivity"] < baseline["emergency_sensitivity"]
    assert "not clinical performance" in baseline["warning"]


def test_development_notification_adapter_never_contacts_recipient() -> None:
    receipt = asyncio.run(
        DevelopmentNoSendAdapter().deliver("SMS", "+0000000000", {"message": "synthetic"})
    )
    assert receipt.startswith("dev-no-send:")
