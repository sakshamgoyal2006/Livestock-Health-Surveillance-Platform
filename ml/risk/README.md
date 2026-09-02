# Risk pipeline

`train_demo.py` records deterministic synthetic dataset provenance and its group
split. `evaluate_demo.py` evaluates the fixed baseline only on held-out FARM_G/H and
writes actual demo metrics; these are not clinical performance.

`train_candidate.py` is the governed, group-aware/time-ordered tree candidate entry
point. It rejects non-authorized provenance and leakage fields and uses class
weighting plus a separate calibration group. It has not been run because no
authorized clinical dataset exists. See `data-contract.json`.
