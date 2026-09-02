from __future__ import annotations

import argparse
import csv
import hashlib
from datetime import datetime
from pathlib import Path

CLASS_ORDER = [
    "SKIN_LESION",
    "OCULAR_NASAL_DISCHARGE",
    "SWELLING",
    "NORMAL_APPEARANCE",
    "OTHER_UNKNOWN",
]
REQUIRED = {
    "image_path",
    "subject_group_id",
    "captured_at",
    "label",
    "provenance",
    "consent_reference",
}


def validate(manifest: Path, image_root: Path) -> dict[str, object]:
    with manifest.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError(
                f"missing columns: {sorted(REQUIRED - set(reader.fieldnames or []))}"
            )
        rows = list(reader)
    if not rows:
        raise ValueError("manifest is empty")
    hashes: dict[str, str] = {}
    groups: set[str] = set()
    for row in rows:
        if row["provenance"] != "AUTHORIZED_CLINICAL":
            raise ValueError(
                "real-image training requires AUTHORIZED_CLINICAL provenance"
            )
        if row["label"] not in CLASS_ORDER:
            raise ValueError(f"unknown label: {row['label']}")
        if not row["consent_reference"].strip():
            raise ValueError("every image requires a consent reference")
        datetime.fromisoformat(row["captured_at"].replace("Z", "+00:00"))
        image = (image_root / row["image_path"]).resolve()
        if image_root.resolve() not in image.parents or not image.is_file():
            raise ValueError(f"missing or out-of-root image: {row['image_path']}")
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        previous = hashes.setdefault(digest, row["subject_group_id"])
        if previous != row["subject_group_id"]:
            raise ValueError("duplicate image bytes occur across subject groups")
        groups.add(row["subject_group_id"])
    if len(groups) < 3:
        raise ValueError(
            "at least three subject groups are required for group-aware splits"
        )
    return {
        "rows": len(rows),
        "subject_groups": len(groups),
        "class_order": CLASS_ORDER,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate an authorized vision manifest"
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("image_root", type=Path)
    args = parser.parse_args()
    print(validate(args.manifest, args.image_root))


if __name__ == "__main__":
    main()
