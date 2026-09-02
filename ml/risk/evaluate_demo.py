from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "synthetic_cp2.csv"
REPORT = ROOT / "reports" / "checkpoint2-demo-evaluation.json"
LABELS = ["LOW", "VET_REVIEW", "EMERGENCY"]


def probabilities(row: dict[str, str]) -> dict[str, float]:
    low = 0.4
    review = 0.8 * int(row["severity_score"] == "1")
    review += 0.45 * int(row["appetite_loss"])
    review += 0.2 * int(row["vaccination_unknown"])
    review += 0.65 * int(int(row["missing_count"]) >= 4)
    emergency = -1.0 + 1.15 * int(row["severity_score"] == "2")
    emergency += 0.9 * int(row["respiration_flag"])
    emergency += 1.1 * int(row["mobility_flag"])
    emergency += 0.9 * int(int(row["mortality_count"]) > 0)
    values = [
        math.exp(score - max(low, review, emergency))
        for score in (low, review, emergency)
    ]
    total = sum(values)
    return dict(zip(LABELS, (value / total for value in values), strict=True))


def safe_ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def main() -> None:
    with DATA.open(encoding="utf-8", newline="") as handle:
        all_rows = list(csv.DictReader(handle))
    test = [row for row in all_rows if row["farm_id"] in {"FARM_G", "FARM_H"}]
    pairs = [(row, probabilities(row)) for row in test]
    confusion = {truth: {predicted: 0 for predicted in LABELS} for truth in LABELS}
    per_class: dict[str, dict[str, float | None]] = {}
    brier = 0.0
    for row, probs in pairs:
        predicted = max(LABELS, key=lambda label: probs[label])
        confusion[row["label"]][predicted] += 1
        brier += sum(
            (probs[label] - int(row["label"] == label)) ** 2 for label in LABELS
        )
    for label in LABELS:
        tp = confusion[label][label]
        fp = sum(confusion[truth][label] for truth in LABELS if truth != label)
        fn = sum(
            confusion[label][predicted] for predicted in LABELS if predicted != label
        )
        precision = safe_ratio(tp, tp + fp)
        recall = safe_ratio(tp, tp + fn)
        f1 = (
            round(2 * precision * recall / (precision + recall), 6)
            if precision is not None and recall is not None and precision + recall
            else None
        )
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1}
    emergency_total = sum(1 for row, _ in pairs if row["label"] == "EMERGENCY")
    emergency_fn = sum(
        1
        for row, probs in pairs
        if row["label"] == "EMERGENCY"
        and max(LABELS, key=lambda label: probs[label]) != "EMERGENCY"
    )
    pr_curve = []
    threshold_analysis = []
    for threshold in (0.2, 0.35, 0.5, 0.65):
        tp = sum(
            1
            for row, probs in pairs
            if row["label"] == "EMERGENCY" and probs["EMERGENCY"] > threshold
        )
        fp = sum(
            1
            for row, probs in pairs
            if row["label"] != "EMERGENCY" and probs["EMERGENCY"] > threshold
        )
        fn = emergency_total - tp
        point = {
            "threshold": threshold,
            "precision": safe_ratio(tp, tp + fp),
            "recall": safe_ratio(tp, tp + fn),
            "false_negatives": fn,
        }
        pr_curve.append(point)
        threshold_analysis.append(point)
    subgroup: dict[str, dict[str, int]] = defaultdict(
        lambda: {"count": 0, "correct": 0}
    )
    for row, probs in pairs:
        subgroup[row["species"]]["count"] += 1
        subgroup[row["species"]]["correct"] += int(
            max(LABELS, key=lambda label: probs[label]) == row["label"]
        )
    report = {
        "warning": "SYNTHETIC DEMO METRICS ONLY; not clinical performance or validation",
        "dataset_provenance": "ml/risk/data/synthetic_cp2.csv; 24 authored synthetic rows",
        "test_split": {
            "groups": ["FARM_G", "FARM_H"],
            "rows": len(test),
            "temporal_period": [
                min(row["event_time"] for row in test),
                max(row["event_time"] for row in test),
            ],
            "group_overlap_with_train_or_calibration": False,
        },
        "model_version": "interpretable-risk-demo-1.0.0",
        "calibration_status": "DEMO_UNVALIDATED",
        "per_class": per_class,
        "emergency_sensitivity": safe_ratio(
            emergency_total - emergency_fn, emergency_total
        ),
        "emergency_false_negative_rate": safe_ratio(emergency_fn, emergency_total),
        "confusion_matrix": confusion,
        "multiclass_brier_score": round(brier / len(pairs), 6),
        "pr_curve_emergency": pr_curve,
        "calibration_bins": "NOT_ESTIMATED_TEST_SET_TOO_SMALL",
        "threshold_analysis": threshold_analysis,
        "subgroup_checks": dict(subgroup),
        "oversampling": "NOT_USED",
        "tree_candidate": "BLOCKED_NO_AUTHORIZED_CLINICAL_DATA",
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
