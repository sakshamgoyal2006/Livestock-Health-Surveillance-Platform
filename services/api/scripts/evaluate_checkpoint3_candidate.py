from __future__ import annotations

import json

from app.operations.mlops import _evaluate, locked_benchmark


def main() -> None:
    report = {
        "scope": "CHECKPOINT_3_VERIFIED_ACTIVE_LEARNING_SAFETY_GATE",
        "dataset": {
            "version": locked_benchmark()["version"],
            "provenance": locked_benchmark()["provenance"],
            "authorization": "SYNTHETIC_DEMO_ONLY",
            "locked": True,
        },
        "current_baseline": _evaluate("BASELINE_EQUIVALENT"),
        "intentional_regression_fixture": _evaluate("INTENTIONAL_REGRESSION_FIXTURE"),
        "promotion_policy": {
            "automatic_promotion": False,
            "manual_approval_required": True,
            "regression_fixture_expected_result": "REJECTED_REGRESSION",
        },
        "clinical_validation": False,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
