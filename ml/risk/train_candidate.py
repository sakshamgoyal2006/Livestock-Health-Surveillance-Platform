"""Train a group-aware, time-ordered tree candidate from authorized clinical data.

This script is intentionally separate from the runtime demo adapter. It rejects
synthetic or ungoverned rows and never uses review/lab/future fields as features.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

FORBIDDEN = {
    "vet_review",
    "verified_label",
    "lab_result",
    "future_outcome",
    "post_triage_action",
}
REQUIRED = {
    "record_id",
    "group_id",
    "event_time",
    "provenance",
    "label",
    "guided_severity",
    "guided_appetite",
    "guided_mobility",
    "guided_respiration",
    "mortality_count",
    "missing_count",
}
LABELS = ["LOW", "VET_REVIEW", "EMERGENCY"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/risk-tree-candidate.joblib")
    )
    parser.add_argument("--seed", type=int, default=26128)
    args = parser.parse_args()
    try:
        import joblib
        import numpy as np
        import pandas as pd
        from sklearn.compose import ColumnTransformer
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import classification_report
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OneHotEncoder
        from sklearn.utils.class_weight import compute_sample_weight
    except ImportError as exc:
        raise SystemExit(
            "Install ml/requirements-training.txt for candidate training"
        ) from exc

    with args.dataset.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        rows = list(reader)
    if missing := REQUIRED - columns:
        raise ValueError(f"missing contract columns: {sorted(missing)}")
    if columns & FORBIDDEN:
        raise ValueError(
            f"target leakage columns present: {sorted(columns & FORBIDDEN)}"
        )
    if not rows or any(row["provenance"] != "AUTHORIZED_CLINICAL" for row in rows):
        raise ValueError("candidate training requires only AUTHORIZED_CLINICAL rows")
    if any(row["label"] not in LABELS for row in rows):
        raise ValueError("unknown urgency label")

    frame = pd.DataFrame(rows)
    frame["event_time"] = pd.to_datetime(frame["event_time"], utc=True, errors="raise")
    group_order = sorted(
        frame["group_id"].unique(),
        key=lambda group: frame.loc[frame["group_id"] == group, "event_time"].min(),
    )
    if len(group_order) < 5:
        raise ValueError("at least five identity groups are required")
    train_end = max(1, int(len(group_order) * 0.6))
    calibration_end = max(train_end + 1, int(len(group_order) * 0.8))
    split_groups = {
        "train": set(group_order[:train_end]),
        "calibration": set(group_order[train_end:calibration_end]),
        "test": set(group_order[calibration_end:]),
    }
    if not split_groups["test"] or any(
        split_groups[left] & split_groups[right]
        for left, right in (
            ("train", "calibration"),
            ("train", "test"),
            ("calibration", "test"),
        )
    ):
        raise ValueError("could not produce disjoint group splits")

    ignored = {"record_id", "group_id", "event_time", "provenance", "label"}
    feature_columns = sorted(columns - ignored)
    categorical = [column for column in feature_columns if column.startswith("guided_")]
    numeric = [column for column in feature_columns if column not in categorical]
    preprocessing = ColumnTransformer(
        [
            (
                "categorical",
                Pipeline(
                    [
                        (
                            "missing",
                            SimpleImputer(strategy="constant", fill_value="MISSING"),
                        ),
                        (
                            "one_hot",
                            OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                        ),
                    ]
                ),
                categorical,
            ),
            ("numeric", SimpleImputer(strategy="median", add_indicator=True), numeric),
        ]
    )
    base = Pipeline(
        [
            ("features", preprocessing),
            (
                "classifier",
                HistGradientBoostingClassifier(
                    max_depth=4,
                    learning_rate=0.05,
                    max_iter=200,
                    random_state=args.seed,
                ),
            ),
        ]
    )

    def subset(name: str):
        return frame[frame["group_id"].isin(split_groups[name])].sort_values(
            "event_time"
        )

    train, calibration, test = subset("train"), subset("calibration"), subset("test")
    weights = compute_sample_weight(class_weight="balanced", y=train["label"])
    base.fit(train[feature_columns], train["label"], classifier__sample_weight=weights)
    calibration_probabilities = np.clip(
        base.predict_proba(calibration[feature_columns]), 1e-8, 1
    )
    calibrator = LogisticRegression(max_iter=1000, random_state=args.seed)
    calibrator.fit(np.log(calibration_probabilities), calibration["label"])
    test_probabilities = calibrator.predict_proba(
        np.log(np.clip(base.predict_proba(test[feature_columns]), 1e-8, 1))
    )
    predictions = calibrator.classes_[np.argmax(test_probabilities, axis=1)]
    report = classification_report(
        test["label"], predictions, labels=LABELS, output_dict=True
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": base,
            "calibrator": calibrator,
            "label_order": LABELS,
            "feature_columns": feature_columns,
            "feature_schema_version": "triage-features-v1.0.0",
            "split_groups": {key: sorted(value) for key, value in split_groups.items()},
            "leakage_exclusions": sorted(FORBIDDEN),
            "class_counts": dict(Counter(frame["label"])),
            "test_report": report,
            "warning": "Candidate only; independent clinical validation and governance approval required",
        },
        args.output,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
