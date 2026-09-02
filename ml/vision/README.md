# Vision pipeline

The runtime uses a deterministic pixel-statistic demo adapter behind the production
interface. It returns the fixed full class vector, quality, uncertainty, version, and
`OTHER_UNKNOWN` behavior; it is not a learned clinical model.

`validate_manifest.py` enforces the authorized real-image contract before optional ML
imports. `train_transfer.py` is a reproducible EfficientNet transfer-learning
candidate entry point with subject-group/time ordering and class weighting. It has
not been run because no governed clinical image dataset is present.
