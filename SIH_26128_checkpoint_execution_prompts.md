# SIH 26128 — Checkpoint-Controlled Execution Prompts

Use this file together with `SIH_26128_master_execution_prompt.md`.

The master prompt is the authoritative product and engineering specification. The prompts below control execution so the coding agent builds and verifies the project in four dependable checkpoints.

## How to use

1. Open the target repository in Codex or another repository-aware coding agent.
2. Paste or attach `SIH_26128_master_execution_prompt.md`.
3. Immediately paste **Prompt 1** below.
4. Review the checkpoint report and confirm that the stated tests actually pass.
5. Paste Prompt 2, Prompt 3, and Prompt 4 sequentially.
6. If a checkpoint has failures, use the Repair Prompt before proceeding.

Do not paste all four continuation prompts simultaneously. The checkpoint boundary is useful because it forces verification before later components depend on incomplete foundations.

---

## Prompt 1 — Kickoff and Checkpoint 1

```text
Treat the attached/pasted “SIH 26128 Master Execution Prompt” as the authoritative
project specification. You have repository and terminal access. Begin by inspecting
the repository, all project instructions, dependency manifests, current code, tests,
and working-tree state. Preserve relevant existing work and do not perform destructive
repository operations.

Your objective in this turn is CHECKPOINT 1 ONLY: complete Stages 0 through 4 of the
master specification and deliver a working foundational vertical slice.

CHECKPOINT 1 SCOPE

Stage 0 — Scope, clinical boundaries, and acceptance criteria
Stage 1 — Repository, local infrastructure, and shared contracts
Stage 2 — Domain model, PostGIS database, privacy, and auditability
Stage 3 — Authentication and role-specific application shells
Stage 4 — Offline-first reporting and synchronization

Required working vertical slice:

1. A farmer or field worker can authenticate using the development identity adapter.
2. They can create a farm and animal/herd record.
3. They can complete the guided livestock-health report form.
4. They can save and submit a report while the browser is offline.
5. The client stores the mutation durably using a client-generated UUID and
   idempotency key.
6. When connectivity returns, the report synchronizes exactly once.
7. A veterinarian can authenticate and see the synchronized report in a basic queue.
8. The report, location, timestamps, consent, sync state, and audit history are stored
   correctly in PostgreSQL/PostGIS.
9. Optional image, voice, NLP, weather, and ML failures must not prevent the base report
   from being recorded.

IMPLEMENTATION RULES

- If the repository is empty, use the default stack in the master specification:
  Next.js/TypeScript PWA, FastAPI/Python, PostgreSQL/PostGIS, Docker Compose.
- Prefer a modular monolith and clear interfaces over microservices.
- Put external dependencies behind adapters and use local development implementations.
- Never claim clinical validation.
- Seed data must be explicitly marked synthetic.
- Add `.env.example`; never commit secrets.
- Create and maintain `docs/implementation-progress.md`.
- Keep the application runnable throughout the checkpoint.
- Do not implement disconnected UI mockups. Connect the forms, API, database, sync
  queue, authorization, and vet queue end to end.
- Do not continue to Stage 5 or later during this checkpoint.

CHECKPOINT 1 VALIDATION

Before declaring the checkpoint complete:

- Apply all migrations against a fresh PostgreSQL/PostGIS database.
- Run formatting, linting, frontend type checking, backend type/static checks where
  configured, unit tests, API integration tests, and the checkpoint end-to-end test.
- The end-to-end test must disable connectivity, submit at least two reports, restore
  connectivity, confirm exactly-once synchronization, and confirm both reports appear
  in the veterinarian queue without duplicates.
- Test authorization for FARMER, FIELD_WORKER, VETERINARIAN, DISTRICT_OFFICER, and ADMIN.
- Test invalid inputs, missing optional fields, duplicate mutation retries, and stale
  client data.
- Verify the README startup path from a clean local state as far as the environment
  permits.

If a required service cannot run, exhaust safe local alternatives and clearly record
the exact blocker, command, and evidence. Do not mark a test as passed unless it ran.

CHECKPOINT 1 RESPONSE FORMAT

Stop after Checkpoint 1 and report:

1. files/components created or changed;
2. architecture and database decisions;
3. working user flow;
4. exact startup, migration, seed, and test commands;
5. test results with pass/fail counts;
6. known limitations and demo adapters;
7. Checkpoint 1 acceptance criteria, each marked PASS, FAIL, or BLOCKED;
8. whether the repository is safe to continue to Checkpoint 2.

Do not merely provide a plan. Implement Checkpoint 1 now, validate it, and then stop at
the checkpoint boundary.
```

---

## Prompt 2 — Checkpoint 2: Rules and multimodal triage

Paste this only after Checkpoint 1 passes.

```text
Continue the SIH 26128 project using the existing repository and the authoritative
master specification. First inspect the current implementation, git diff/status,
`docs/implementation-progress.md`, and the actual Checkpoint 1 test results. Do not
assume the previous report was correct—run a compact Checkpoint 1 smoke test before
building further.

Your objective in this turn is CHECKPOINT 2 ONLY: complete Stages 5 through 8.

CHECKPOINT 2 SCOPE

Stage 5 — Versioned clinical rules and baseline triage
Stage 6 — Marathi/Hindi/English NLP and speech adapter
Stage 7 — Computer-vision probability-vector pipeline
Stage 8 — Versioned feature builder, late fusion, calibration, and explanations

Required working vertical slice:

1. A synchronized health report triggers a retryable, idempotent triage pipeline.
2. Veterinarian-reviewed/demo-labelled red-flag rules run first and can override ML.
3. Guided symptoms are the trusted primary input.
4. Marathi, Hindi, English, and Romanized-language fixtures can be converted into a
   strict symptom schema using the local deterministic NLP adapter.
5. Optional speech is represented by an adapter; the local/demo path works without
   paid credentials.
6. An uploaded photograph passes security and image-quality checks.
7. The vision adapter returns a complete, ordered probability vector plus quality,
   uncertainty, model version, and OTHER_UNKNOWN behavior.
8. The feature builder combines clinical, CV, animal-history, vaccination, weather,
   GIS-context, and missingness features using a versioned schema.
9. Missing modalities remain missing and have explicit missingness indicators. Never
   interpret a missing image, NLP result, or weather observation as zero risk.
10. The risk engine returns calibrated or clearly demo-labelled probabilities for LOW,
    VET_REVIEW, and EMERGENCY.
11. The decision engine returns both:
    a. suspected syndrome/visible-condition likelihoods; and
    b. a separate urgency tier.
12. The API/UI displays careful explanations, uncertainty, model/rule versions, and
    the decision trace without presenting an AI output as a confirmed diagnosis.

MODEL REQUIREMENTS

- Build an interpretable baseline first and then a tree-based candidate model only if
  data/contracts permit.
- With no authorized clinical dataset, use deterministic adapters and synthetic
  labelled examples for the end-to-end demo. Supply reproducible real-training scripts
  and data contracts, but do not fabricate model accuracy.
- Use group-aware/temporal splits where identities exist.
- Prevent target leakage from vet decisions, lab outcomes, or future information.
- Prefer class weighting and calibrated probabilities.
- If oversampling is tested, apply it only within training folds and never to the
  validation or test set.
- Keep thresholds in versioned configuration. `P(EMERGENCY) > 0.35` may be included as
  an explicitly unvalidated demo setting, never as a universal clinical threshold.
- Emergency rules override model probabilities.
- Insufficient or conflicting information should normally route to VET_REVIEW rather
  than LOW.
- SHAP values, when used, must be described as feature contributions—not causal
  percentage changes.

CHECKPOINT 2 VALIDATION

Run and record:

- Checkpoint 1 regression smoke tests;
- table-driven rule tests, including precedence and boundary conditions;
- multilingual NLP fixtures with negation, ambiguity, Romanized Marathi/Hindi, and
  malformed provider responses;
- image validation, blur/exposure/size rejection, class-order, unknown-class, and
  model-outage tests;
- missing-modality combinations: form only, text only, image only, no weather, and
  partial history;
- feature-schema and model-version compatibility tests;
- reproducible evaluation script and report using only available authorized/demo data;
- calibration/threshold report without invented metrics;
- API integration and UI end-to-end triage tests;
- formatter, linter, type checker, unit tests, and integration tests.

CHECKPOINT 2 RESPONSE FORMAT

Stop after Checkpoint 2 and report:

1. implemented NLP, CV, rule, feature, and risk components;
2. exact modality and fusion contracts;
3. what is a real implementation versus a deterministic demo adapter;
4. model/data limitations;
5. exact training, evaluation, and test commands;
6. actual metrics produced, if any, with dataset provenance;
7. Checkpoint 2 criteria marked PASS, FAIL, or BLOCKED;
8. whether the system is safe to continue to Checkpoint 3.

Do not proceed to veterinarian verification, GIS outbreak workflow, or MLOps stages
beyond interfaces required by this checkpoint.
```

---

## Prompt 3 — Checkpoint 3: HITL, GIS, alerts, and MLOps

Paste this only after Checkpoint 2 passes.

```text
Continue the SIH 26128 project from the existing repository. Re-read the master
specification, inspect `docs/implementation-progress.md`, review working-tree changes,
and run compact regression smoke tests for Checkpoints 1 and 2 before editing.

Your objective in this turn is CHECKPOINT 3 ONLY: complete Stages 9 through 12.

CHECKPOINT 3 SCOPE

Stage 9 — Veterinarian human-in-the-loop case management
Stage 10 — GIS surveillance and temporal outbreak detection
Stage 11 — Multilingual advisories, alerts, lab referrals, and escalation
Stage 12 — Verified active-learning and MLOps lifecycle

Required working vertical slice:

1. Triage creates an authorized veterinarian case with an auditable state machine.
2. The vet sees raw observations, media, quality/uncertainty, rules, model versions,
   condition probabilities, urgency probabilities, explanations, and nearby context.
3. The vet can confirm, correct, mark inconclusive, request a sample, record follow-up,
   or escalate.
4. Suspected, vet-verified, and lab-confirmed statuses remain separate everywhere.
5. Only authorized vet/lab outcomes can create retraining candidates.
6. The original prediction remains immutable and separate from verified ground truth.
7. PostGIS APIs and the dashboard provide authorized point views and privacy-preserving
   village/block/district aggregates.
8. GIS uses proximity, time windows, historical baselines, minimum case counts, and
   status confidence. Spatial density alone must not be labelled a confirmed outbreak.
9. Weather is optional and supplied through a cached adapter.
10. Advisories are template based and available in Marathi, Hindi, and English.
11. Alerts use an outbox, deduplication, retries, acknowledgement, escalation, and a
    development adapter that never contacts real recipients.
12. Lab referral and result workflows update the authoritative case outcome.
13. A verified active-learning pipeline can build an immutable candidate dataset,
    train/evaluate a candidate or deterministic demo candidate, compare it with the
    current model, reject regression, and require explicit manual promotion.
14. No unverified prediction is used as a training label and no model auto-deploys.

GIS DEMONSTRATION DATA

Seed a chronological, clearly synthetic scenario:

- historical baseline for Village A and nearby Village B;
- Day 1: a small number of suspected reports in Village A;
- Day 2: a meaningful rise in Village A and one nearby report;
- live demo: an offline report from Village B synchronizes;
- dashboard updates a hotspot CANDIDATE, not a confirmed outbreak;
- a vet verifies or corrects the case;
- suspected and verified map counts update independently;
- an officer acknowledges the hotspot candidate.

ACTIVE-LEARNING SAFETY

- Never pseudo-label from `P(EMERGENCY)` or any model prediction.
- Store retraining candidates in a staging queue.
- Require verification provenance, quality review, and deduplication.
- Train in batches, not one sample at a time.
- Preserve locked benchmark data and evaluate calibration and safety regressions.
- Track dataset, code, feature schema, thresholds, artifacts, and checksums.
- Require an authorized approval record before promotion.
- Support rollback to the previous model version.

CHECKPOINT 3 VALIDATION

Run and record:

- Checkpoints 1 and 2 regression smoke tests;
- role/permission and state-transition tests;
- invalid or unauthorized verification tests;
- inconclusive, lab-pending, lab-confirmed, and corrected-label branches;
- PostGIS proximity, aggregation, temporal-baseline, and hotspot-status tests;
- suspected-versus-verified map rendering tests;
- alert deduplication, retry, acknowledgement, rate-limit, and development-no-send tests;
- retraining-candidate provenance and pseudo-label rejection tests;
- candidate evaluation, regression rejection, approval, promotion, and rollback tests;
- complete farmer -> sync -> triage -> vet -> GIS -> verified queue end-to-end test;
- formatting, linting, type checking, unit, integration, and E2E suites.

CHECKPOINT 3 RESPONSE FORMAT

Stop after Checkpoint 3 and report:

1. complete operational workflow;
2. case state machine and permissions;
3. GIS and outbreak-candidate algorithm;
4. alert/referral behavior and external adapters;
5. training-data provenance and model-promotion controls;
6. exact seed/demo and test commands;
7. Checkpoint 3 criteria marked PASS, FAIL, or BLOCKED;
8. whether the system is safe to continue to final hardening.

Do not claim field readiness or clinical validation.
```

---

## Prompt 4 — Checkpoint 4: Hardening, deployment, and SIH demonstration

Paste this only after Checkpoint 3 passes.

```text
Complete the SIH 26128 project from the existing repository. Re-read the master
specification, inspect all progress documentation and working-tree changes, and run a
compact regression suite for Checkpoints 1 through 3 before editing.

Your objective is FINAL CHECKPOINT 4: complete Stages 13 and 14, repair any earlier
acceptance gaps, and deliver a reproducible hackathon-ready prototype.

CHECKPOINT 4 SCOPE

Stage 13 — Reliability, security, privacy, accessibility, and performance
Stage 14 — Deployment, deterministic demonstration, and technical handoff

Required final outcomes:

1. A fresh developer can start the complete system using documented commands.
2. Database migrations and synthetic seed data run from an empty environment.
3. The complete farmer -> offline -> sync -> triage -> vet -> GIS -> verification ->
   retraining-queue scenario is reproducible.
4. Docker images and Docker Compose configuration work as far as the environment permits.
5. Authentication/authorization, media access, file validation, input validation,
   idempotency, rate limiting, log redaction, and audit behavior are tested.
6. Provider/model/job failures produce safe degraded behavior rather than lost reports
   or false low-risk decisions.
7. Marathi, Hindi, and English layouts are usable on mobile-sized screens.
8. Maps and batch sync have basic performance coverage.
9. Health/readiness endpoints and observable component status exist.
10. Documentation accurately separates working features, demo adapters, future
    integrations, and veterinarian/field-validation requirements.

REQUIRED DOCUMENTATION

- root README with exact prerequisites and commands;
- product requirements and traceability;
- architecture and sequence diagrams;
- database ER diagram/data dictionary;
- OpenAPI/API usage guide;
- offline-sync design and conflict rules;
- clinical-safety and privacy boundaries;
- model cards, dataset cards, evaluation and threshold reports;
- GIS/hotspot methodology;
- deployment, operations, backup/restore, monitoring, and rollback notes;
- test report based on actual executed commands;
- known limitations and production-readiness gap analysis;
- concise SIH demo script and fallback demo plan.

FINAL DEMO SCRIPT

Make the seeded demonstration show:

1. farmer selects Marathi/Hindi/English;
2. farmer creates or selects an animal;
3. connectivity is disabled;
4. farmer submits guided symptoms and optional media;
5. local preliminary red-flag guidance appears with an offline disclaimer;
6. connectivity returns and the report synchronizes exactly once;
7. server triage shows condition probabilities, separate urgency probabilities,
   uncertainty, rule/model versions, and careful explanations;
8. vet reviews and corrects/verifies the report;
9. GIS changes a hotspot candidate while keeping suspected and verified counts separate;
10. verified evidence enters the retraining staging queue;
11. a candidate model comparison refuses regression and requires manual promotion.

FINAL VALIDATION

Create and run one root validation command covering formatting, linting, type checking,
unit tests, integration tests, and an end-to-end smoke test. Also run focused security,
accessibility, localization, offline, spatial, alert, and MLOps tests. Record exact
commands and outputs. Fix failures introduced by the project. Do not say “all tests
pass” unless the complete stated suite ran successfully.

FINAL RESPONSE FORMAT

Report:

1. concise product outcome;
2. final architecture;
3. checkpoint-by-checkpoint completion table;
4. working features versus demo adapters;
5. exact startup, migration, seed, demo, training, evaluation, and test commands;
6. actual test results and model metrics, without invented values;
7. security, privacy, offline, data, and clinical limitations;
8. paths to all important source files and documentation;
9. safest next steps for veterinarian review, dataset approval, and field pilot;
10. final definition-of-done items marked PASS, FAIL, or BLOCKED.

Do not stop at a review or plan. Implement repairs and final hardening, run validation,
and deliver the integrated prototype.
```

---

## Repair Prompt — Use when a checkpoint has failures

```text
Do not start the next SIH 26128 checkpoint yet.

Inspect the repository, `docs/implementation-progress.md`, and the most recent
checkpoint report. Re-run every failed or blocked acceptance test that can run in the
current environment. Determine root causes, implement the smallest robust fixes, and
run the full checkpoint regression suite again.

Do not bypass tests, weaken assertions, hardcode passing outputs, replace real
integration paths with disconnected mockups, or mark unavailable services as passed.
Preserve user changes and avoid destructive repository operations.

Finish by listing each previously failed/blocked criterion with:

- root cause;
- files changed;
- exact verification command;
- actual result;
- new status: PASS, FAIL, or BLOCKED.

Proceed to the next checkpoint only if all safety-critical and foundational criteria
pass. Otherwise stop with precise remaining blockers and evidence.
```

