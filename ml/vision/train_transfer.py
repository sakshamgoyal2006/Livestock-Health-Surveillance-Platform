"""Reproducible real-image training entry point; not run without authorized data.

The validator deliberately runs before optional ML imports. This checkpoint ships no
clinical image dataset and therefore produces no trained weights or accuracy claim.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from validate_manifest import CLASS_ORDER, validate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("image_root", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/vision-candidate.pt")
    )
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--seed", type=int, default=26128)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    evidence = validate(args.manifest, args.image_root)
    if args.validate_only:
        print(json.dumps(evidence, indent=2))
        return

    try:
        import torch
        from PIL import Image
        from torch import nn
        from torch.utils.data import DataLoader, Dataset
        from torchvision.models import EfficientNet_B0_Weights, efficientnet_b0
    except ImportError as exc:
        raise SystemExit(
            "Install ml/requirements-training.txt for real training"
        ) from exc

    import csv
    from datetime import datetime

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    with args.manifest.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    groups = sorted(
        {row["subject_group_id"] for row in rows},
        key=lambda group: min(
            datetime.fromisoformat(row["captured_at"].replace("Z", "+00:00"))
            for row in rows
            if row["subject_group_id"] == group
        ),
    )
    train_groups = set(groups[: max(1, int(len(groups) * 0.7))])
    test_groups = set(groups[max(1, int(len(groups) * 0.85)) :])
    validation_groups = set(groups) - train_groups - test_groups
    if not validation_groups or not test_groups:
        raise ValueError(
            "more subject groups are required for train/validation/test splits"
        )

    weights = EfficientNet_B0_Weights.DEFAULT
    transform = weights.transforms()

    class ManifestDataset(Dataset):
        def __init__(self, selected_groups: set[str]) -> None:
            self.rows = [
                row for row in rows if row["subject_group_id"] in selected_groups
            ]

        def __len__(self) -> int:
            return len(self.rows)

        def __getitem__(self, index: int):
            row = self.rows[index]
            image = Image.open(args.image_root / row["image_path"]).convert("RGB")
            return transform(image), CLASS_ORDER.index(row["label"])

    train_data = ManifestDataset(train_groups)
    counts = Counter(
        int(label.item()) for _, label in DataLoader(train_data, batch_size=1)
    )
    class_weights = torch.tensor(
        [
            len(train_data) / max(1, len(CLASS_ORDER) * counts.get(index, 0))
            for index in range(5)
        ]
    )
    model = efficientnet_b0(weights=weights)
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(CLASS_ORDER))
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    loss_fn = nn.CrossEntropyLoss(weight=class_weights)
    model.train()
    for _ in range(args.epochs):
        for images, labels in DataLoader(train_data, batch_size=16, shuffle=True):
            optimizer.zero_grad()
            loss = loss_fn(model(images), labels)
            loss.backward()
            optimizer.step()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "class_order": CLASS_ORDER,
            "model_family": "efficientnet_b0_transfer_candidate",
            "calibration_status": "UNCALIBRATED_CANDIDATE",
            "seed": args.seed,
            "split_groups": {
                "train": sorted(train_groups),
                "validation": sorted(validation_groups),
                "test": sorted(test_groups),
            },
        },
        args.output,
    )
    print(
        f"Wrote unvalidated candidate weights to {args.output}; evaluation is still required"
    )


if __name__ == "__main__":
    main()
