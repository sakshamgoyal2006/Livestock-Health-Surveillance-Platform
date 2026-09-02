from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "synthetic_cp2.csv"
ARTIFACT = ROOT / "artifacts" / "interpretable-demo-v1.json"
LABELS = ["LOW", "VET_REVIEW", "EMERGENCY"]
FORBIDDEN = {"vet_review", "verified_label", "lab_result", "future_outcome"}


def load_rows() -> list[dict[str, str]]:
    with DATA.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or set(rows[0]).intersection(FORBIDDEN):
        raise ValueError("Dataset is empty or contains target-leakage fields")
    if any(row["provenance"] != "SYNTHETIC_DEMO" for row in rows):
        raise ValueError(
            "Checkpoint 2 demo training accepts only explicitly synthetic rows"
        )
    if any(row["label"] not in LABELS for row in rows):
        raise ValueError("Unknown target label")
    return rows


def main() -> None:
    rows = load_rows()
    groups = sorted({row["farm_id"] for row in rows})
    split = {
        "train_groups": groups[:4],
        "calibration_groups": groups[4:6],
        "test_groups": groups[6:],
    }
    if set(split["train_groups"]) & set(split["test_groups"]):
        raise ValueError("Group leakage detected")
    artifact = {
        "model_version": "interpretable-risk-demo-1.0.0",
        "feature_schema_version": "triage-features-v1.0.0",
        "threshold_version": "thresholds-demo-1.0.0",
        "calibration_status": "DEMO_UNVALIDATED",
        "dataset": str(DATA.relative_to(ROOT)),
        "dataset_sha256": hashlib.sha256(DATA.read_bytes()).hexdigest(),
        "provenance": "24 deterministic synthetic demonstration rows; no clinical claims",
        "split": split,
        "label_counts": Counter(row["label"] for row in rows),
        "class_weight_policy": "balanced conceptual baseline; no oversampling performed",
        "tree_candidate": "NOT_TRAINED_NO_AUTHORIZED_CLINICAL_DATA",
        "leakage_exclusions": sorted(FORBIDDEN),
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"Wrote {ARTIFACT} from {len(rows)} explicitly synthetic rows")


if __name__ == "__main__":
    main()
