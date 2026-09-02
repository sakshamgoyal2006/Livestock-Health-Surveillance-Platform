# Master Execution Prompt — SIH 26128 Livestock Health Surveillance Platform

Copy everything below this line into a capable coding agent that has access to the target repository.

---

You are the principal software architect, full-stack engineer, ML engineer, GIS engineer, QA engineer, and technical writer responsible for building a complete working project for SIH Statement ID 26128:

> Efficient systems for early detection, prevention, and management of livestock diseases and animal health issues.

Build a multilingual, offline-capable livestock-health surveillance and veterinary decision-support platform for Maharashtra. It must let farmers and field workers report animal symptoms and mortality, optionally attach images or voice, produce an explainable preliminary triage result, route cases to veterinarians, maintain animal/herd health records, visualize emerging risk geographically, support lab referral and escalation, and learn only from veterinarian-verified outcomes.

The product is a **triage and early-warning system**, not an autonomous diagnostic system. Never present an AI result as a confirmed diagnosis. Use wording such as “suspected condition,” “preliminary risk,” and “veterinary verification required.” Emergency clinical rules and veterinarian decisions take precedence over model output.

## 1. Operating instructions

1. Inspect the repository, its instructions, current code, dependency manifests, environment files, and test setup before editing. Preserve relevant existing work.
2. If the repository is empty, create the monorepo described below. If it already has a reasonable stack, adapt the plan instead of replacing working code unnecessarily.
3. Create and maintain `docs/implementation-progress.md`. Record each stage, decisions, assumptions, commands run, test results, limitations, and remaining work.
4. Execute the stages in order. Do not stop after planning or scaffolding. Implement, test, and document each stage, then continue while safe and feasible.
5. At the end of every stage:
   - run the relevant formatter, linter, type checker, unit tests, and integration tests;
   - fix failures caused by the work;
   - record evidence in `docs/implementation-progress.md`;
   - make the smallest reasonable commit if repository policy permits commits.
6. Never invent clinical accuracy, dataset provenance, veterinarian approval, field-pilot results, or government integrations. Label generated records as synthetic demo data.
7. Do not silently depend on paid or proprietary services. Put speech, translation, weather, SMS, WhatsApp, object storage, and external LLMs behind interfaces. Supply local/dev adapters so the complete demonstration works without external credentials.
8. Never place secrets in source control. Provide `.env.example`, validate configuration at startup, and redact sensitive values from logs.
9. Do not automatically dispatch public-health actions, publish an outbreak, retrain a production model from predictions, or deploy a new model. These operations require authorized human review.
10. If a real dataset is absent, build validated data contracts, deterministic demo adapters, reproducible training scripts, and a clearly labelled synthetic dataset. Do not download or claim rights to a dataset without authorization.

## 2. Final product scope

Support these roles:

- `FARMER`: register animals/herds, submit reports, receive advisories, view case status.
- `FIELD_WORKER`: submit reports on behalf of farmers and assist with offline collection.
- `VETERINARIAN`: review triage results and evidence, request samples, confirm/correct outcomes, prescribe next actions.
- `DISTRICT_OFFICER`: monitor queues, trends, vaccination coverage, hotspots, and escalations.
- `ADMIN`: manage reference data, users, feature flags, model versions, and audit access.

Support these core workflows:

1. Farmer creates an animal/herd profile.
2. Farmer completes a guided symptom questionnaire in Marathi, Hindi, or English.
3. Farmer may add free text, voice, photographs, mortality information, and location.
4. The app validates inputs and works offline using a durable local queue.
5. Offline mode immediately runs deterministic red-flag rules and marks the result as preliminary. Heavy analysis occurs after synchronization.
6. Server-side NLP converts free text/transcripts to a strict symptom schema.
7. The image pipeline checks quality and returns a probability vector across supported visible-condition classes plus `OTHER_UNKNOWN`.
8. Context enrichment adds animal history, vaccination, weather, season, location, and nearby recent-case features when available.
9. A late-fusion risk engine outputs calibrated probabilities for `LOW`, `VET_REVIEW`, and `EMERGENCY`.
10. A rule engine applies clinician-approved overrides and configurable thresholds.
11. The farmer receives safe, multilingual advice; a vet receives appropriate cases; officials see aggregates rather than premature confirmed-outbreak claims.
12. The veterinarian confirms, corrects, or marks the case inconclusive and may create a lab referral.
13. Only veterinarian/lab-verified examples can enter a retraining candidate queue.
14. New models are trained in batches, evaluated against locked benchmark data, reviewed, versioned, and manually promoted.

## 3. Architecture to implement

Use a modular monolith for the initial complete project, with boundaries that can later become services. Prefer simplicity, testability, and a reliable end-to-end flow over unnecessary microservices.

Default stack when no compatible stack exists:

- Web/PWA: Next.js + TypeScript, responsive UI, installable service worker, IndexedDB offline queue, accessible components, Leaflet with OpenStreetMap tiles.
- API: Python + FastAPI + Pydantic + SQLAlchemy/Alembic.
- Database: PostgreSQL with PostGIS.
- Background work: a job abstraction with an in-process development adapter; optionally Redis-backed workers in production.
- ML: scikit-learn plus XGBoost or CatBoost for tabular risk; PyTorch with MobileNetV3 or EfficientNet-B0 transfer-learning scripts for images; SHAP-compatible explanation adapter.
- Object/media storage: local filesystem adapter for development and S3-compatible adapter interface for production.
- Testing: pytest for backend/ML, the frontend stack’s unit-test runner, Playwright for critical end-to-end flows.
- Packaging/deployment: Dockerfiles and Docker Compose for local development; deployment notes that do not assume a particular cloud vendor.

Use this logical data flow:

```text
Farmer/Field Worker
  -> guided form + optional text/voice/image + location
  -> client validation + consent + offline mutation queue
  -> sync API with idempotency key
  -> canonical health report
  -> NLP/image/context enrichment jobs
  -> versioned feature builder
  -> red-flag rules + calibrated late-fusion model
  -> explainable triage decision
  -> farmer advisory / vet queue / officer alert
  -> vet review / lab referral / final outcome
  -> verified retraining candidate
  -> batch evaluation and manual model promotion
```

Every asynchronous component must be idempotent, retryable, observable, and tolerant of optional inputs. A missing photo is not a zero-risk photo. Preserve `null` plus a missingness indicator, and use training-consistent imputation. The feature schema must be versioned.

## 4. Finalized implementation stages

### Stage 0 — Scope, clinical boundaries, and acceptance criteria

Create:

- `docs/product-requirements.md`
- `docs/clinical-safety-boundaries.md`
- `docs/architecture.md`
- `docs/acceptance-criteria.md`

Define a narrow demo scope: cattle/buffalo and a small configurable set of syndrome/visible-condition classes. Do not imply that every livestock disease is visually diagnosable. Define red flags, risk tiers, user actions, non-goals, escalation ownership, supported languages, offline behavior, and measurable success criteria.

Initial success metrics should include report-completion time, sync success, high-risk sensitivity on the approved test set, false-negative rate, probability calibration, vet-review turnaround time, alert precision, accessibility, and offline recovery. Mark all unmeasured clinical targets as “requires domain validation.”

Exit gate: requirements traceability maps every problem-statement outcome to at least one product feature and test.

### Stage 1 — Repository, local infrastructure, and contracts

Set up the monorepo, local commands, formatting, linting, type checking, tests, Docker Compose, PostgreSQL/PostGIS, migration tooling, environment validation, seed commands, CI, structured logging, request IDs, health/readiness endpoints, and API documentation.

Recommended layout:

```text
apps/web/
services/api/
packages/contracts/
ml/risk/
ml/vision/
ml/nlp/
infra/
docs/
tests/e2e/
```

Generate shared API contracts from OpenAPI or an equivalent single source of truth. Add a one-command developer startup and a one-command validation suite.

Exit gate: a new developer can start the system from the README and see the web app, API health response, and PostGIS connectivity.

### Stage 2 — Domain model, database, privacy, and auditability

Implement migrations and repositories for at least:

- users, roles, farmers, field workers, veterinarians;
- farms, herds, animals, ownership/assignment;
- health reports, mortality reports, symptom observations, media assets;
- vaccination records, treatment records, disease history;
- risk assessments, feature snapshots, explanations, model versions;
- vet reviews, case assignments, status history, lab referrals/results;
- advisories, alert events, notification outbox;
- administrative areas and location points;
- weather snapshots and surveillance aggregates;
- retraining candidates, dataset versions, promotion approvals;
- sync mutations and audit logs.

Use UUIDs generated client-side where offline creation is needed. Store location as PostGIS `GEOGRAPHY(Point, 4326)` and create spatial indexes. Keep `created_at_device`, `received_at_server`, `updated_at`, `sync_status`, `client_mutation_id`, and optimistic concurrency metadata.

Separate raw observations, derived features, model results, human decisions, and lab-confirmed truth. Store model probabilities and explanations with `model_version` and `feature_schema_version`. Do not make JSONB the only store for important searchable clinical fields; use typed columns/tables for stable fields and JSONB only for versioned flexible payloads.

Implement minimal-data collection, consent recording, role-based access, media authorization, EXIF removal from images, audit trails, retention hooks, and safe log redaction.

Exit gate: migrations apply from an empty database, seed data loads, spatial queries work, and access/audit tests pass.

### Stage 3 — Identity and role-specific application shells

Implement secure development authentication and an adapter boundary for production identity. Add authorization on both API and UI routes. Create role-specific navigation and dashboards.

Farmer/field-worker screens:

- home and urgent-report entry;
- animal/herd registry;
- guided report wizard;
- offline/sync center;
- report history and status;
- multilingual advisory view.

Veterinarian screens:

- prioritized case queue;
- case evidence and risk breakdown;
- confirm/correct/inconclusive review form;
- lab referral and sample status;
- follow-up/treatment status.

Officer/admin screens:

- operational overview;
- GIS surveillance map;
- alert and escalation queue;
- vaccination/trend views;
- model and reference-data status;
- audit viewer restricted by role.

Exit gate: authorization tests prove every role can access only permitted data and operations.

### Stage 4 — Offline-first reporting and synchronization

Build a stepwise report wizard with large touch targets and simple language. Guided fields are primary; free text, voice, and image are optional. Capture species, age band, symptom onset, severity, appetite, water intake, mobility, respiration, visible lesions, discharge, temperature if known, vaccination, recent movement/contact, mortality, location precision, and consent.

Implement:

- local drafts and IndexedDB mutation queue;
- service-worker caching for the application shell and reference questionnaire;
- client-generated UUID and idempotency key;
- resumable/compressed media handling;
- exponential retry with visible status;
- batch sync endpoint;
- duplicate detection and optimistic conflict handling;
- device and server timestamps;
- deterministic red-flag checks available offline;
- a clear label that offline results are preliminary and may change after sync.

Do not require GPS; allow village selection and reduced-precision coordinates. Do not block report submission when optional media, translation, weather, or a model is unavailable.

Exit gate: an end-to-end test disables connectivity, submits two reports, restores connectivity, synchronizes exactly once, and shows both cases in the vet queue without duplicates.

### Stage 5 — Clinical rules and baseline triage

Implement a versioned rules engine before ML. Keep rules in validated configuration with provenance, review metadata, effective dates, and tests. Include placeholders for veterinarian-approved emergency signs, but label unapproved demonstration rules clearly.

The decision policy must be:

1. validated emergency rule override;
2. otherwise calibrated model probabilities;
3. otherwise safe baseline rules when the model is unavailable;
4. otherwise request vet review when information is insufficient.

Never silently downgrade a case because a model or modality failed. Emit a machine-readable decision trace.

Exit gate: table-driven tests cover every rule, boundary value, missing field, conflict, and model-outage path.

### Stage 6 — Multilingual NLP and speech adapter

Build a strict symptom-extraction contract. Required output fields include detected language, normalized text, symptom entities, negations, duration, severity, body site, uncertainty, source spans where possible, and parser confidence.

Use a hybrid approach:

- the guided form is the trusted primary source;
- a curated Marathi/Hindi/English/transliterated lexicon handles common terms and local synonyms;
- a deterministic parser provides an offline/dev baseline;
- optional multilingual transformer or external LLM adapters may enrich the result;
- every LLM response must be schema-validated, bounded, treated as untrusted input, and rejected safely when invalid;
- free-text extraction cannot overwrite an explicit guided answer without recording the conflict.

Put speech-to-text behind an adapter and provide a transcript-entry/demo adapter. Show extracted symptoms to the user for confirmation when feasible.

Exit gate: multilingual fixtures include native scripts, Romanized Marathi/Hindi, negations, ambiguous slang, and malformed responses. The pipeline degrades safely when speech/translation services fail.

### Stage 7 — Computer-vision probability pipeline

Define visible-condition classes plus `NORMAL_APPEARANCE` and `OTHER_UNKNOWN`. Implement:

- image MIME/size/security validation;
- EXIF removal;
- blur, exposure, resolution, and subject-quality checks;
- a deterministic development inference adapter;
- transfer-learning and evaluation scripts for MobileNetV3 or EfficientNet-B0;
- group-aware splits by animal/farm/source to prevent leakage;
- class imbalance handling limited to training data;
- probability calibration;
- an uncertainty/OOD policy;
- model card and dataset documentation.

Output a complete versioned probability vector, for example:

```json
{
  "class_order": ["VISIBLE_CONDITION_A", "VISIBLE_CONDITION_B", "NORMAL_APPEARANCE", "OTHER_UNKNOWN"],
  "probabilities": [0.42, 0.31, 0.08, 0.19],
  "quality_score": 0.87,
  "uncertain": true,
  "model_version": "vision-dev-1"
}
```

The UI must not convert this vector directly into a diagnosis. If quality is poor or uncertainty is high, request another image or vet review.

Exit gate: the inference contract, quality rejection, class order, calibration report, leakage checks, and unknown-class behavior are tested.

### Stage 8 — Feature builder, late fusion, calibration, and explanations

Build a versioned feature pipeline that combines:

- guided and NLP-derived symptoms;
- CV probability vector and quality;
- animal/herd history;
- vaccination status;
- weather/season when available;
- location precision;
- recent nearby suspected/verified cases;
- missingness indicators for every optional modality.

Do not assign zero to a missing CV/NLP/weather value without a missing flag and training-consistent imputation. Prevent target leakage: do not use vet diagnosis, lab results, future outcomes, or post-triage actions as inference-time features.

Train an interpretable baseline and then a tree-based candidate model. Prefer class weighting and grouped/temporal cross-validation. If oversampling is evaluated, apply it only inside training folds and use a method appropriate for mixed categorical/numerical data; never contaminate validation/test sets.

Return `predict_proba` for `LOW`, `VET_REVIEW`, and `EMERGENCY`. Calibrate probabilities on held-out data. Keep thresholds in versioned configuration; `P(EMERGENCY) > 0.35` may be a demo starting point but must not be presented as clinically validated. Select thresholds using cost-sensitive evaluation and veterinarian review.

Generate explanations through a stable explanation interface. SHAP may be used for supported tree models, but label values as feature contributions—not literal causal percentage increases. Convert top contributions into careful human-readable reasons and retain the underlying feature/value/contribution data.

Exit gate: reproducible evaluation reports include per-class precision/recall/F1, emergency sensitivity and false-negative rate, confusion matrix, PR curves, calibration/Brier score, subgroup checks, threshold analysis, missing-modality tests, and a model card.

### Stage 9 — Veterinary human-in-the-loop case management

Implement the authoritative case state machine, for example:

```text
DRAFT -> SUBMITTED -> TRIAGED -> ASSIGNED -> UNDER_REVIEW
      -> SAMPLE_REQUESTED -> LAB_PENDING -> VERIFIED/INCONCLUSIVE/CLOSED
```

Every transition must be permission-checked, timestamped, and audited. A vet must be able to see raw observations, media, modality status, model version, calibrated probabilities, rule overrides, explanations, nearby context, and uncertainty. The vet can confirm a label, correct it, mark it inconclusive, request a sample, add treatment/follow-up, or escalate.

Only sufficiently verified outcomes may create a `retraining_candidate`. Preserve the original prediction separately. Never relabel training data from the model’s own prediction. Protect against duplicate animals/images, label conflicts, poor image quality, and unverified users.

Exit gate: the full farmer-to-vet flow works, unauthorized verification is rejected, and the verified outcome enters the staging queue without altering the production model.

### Stage 10 — GIS surveillance and outbreak detection

Implement privacy-preserving maps and spatial APIs using PostGIS. Provide:

- individual authorized case view for vets;
- aggregated village/block/district view for officials;
- filters for date, species, syndrome, status, and risk tier;
- marker clustering, choropleth/heat layers, legends, uncertainty, and last-updated time;
- proximity queries with `ST_DWithin`;
- server-side clustering/aggregation for scale;
- separate counts for suspected, vet-verified, and lab-confirmed reports.

Do not equate a dense cluster with a confirmed outbreak. Combine spatial concentration with a time window and a historical baseline. Implement a transparent initial detector such as rolling rates/EWMA plus minimum case count and optional spatial clustering. Store detector version, baseline, observed count, confidence/status, and reviewer action.

Use a weather-provider adapter and cached snapshots. The system must operate without weather data and expose its absence as uncertainty.

Exit gate: seeded chronological demo data tells a reproducible story—an initial baseline, an increase in one village, a nearby live report, a hotspot candidate, and an officer acknowledgement—while keeping suspected and confirmed states visually distinct.

### Stage 11 — Advisories, alerts, referrals, and coordinated response

Create templated Marathi/Hindi/English advisories reviewed through a content workflow. Avoid free-form generative medical instructions by default. Support safe immediate actions such as isolation guidance only when approved, contact-vet instructions, and emergency contact placeholders.

Implement an outbox pattern and adapters for in-app notifications, SMS/WhatsApp, and email. The development adapter records notifications without sending them. Deduplicate alerts, rate-limit them, audit delivery attempts, retry transient failures, and provide acknowledgement/escalation states.

Implement lab referral, sample identifier, chain-of-custody status, result recording, and linkage to the final case outcome. Do not fabricate real laboratory integration.

Exit gate: tests prove correct audience, language, deduplication, retries, acknowledgement, and no external transmission in development mode.

### Stage 12 — MLOps and verified active-learning lifecycle

Implement a safe batch-learning workflow:

```text
verified cases
  -> retraining candidate review
  -> immutable dataset version
  -> group/temporal split
  -> train candidate
  -> locked benchmark + safety evaluation
  -> comparison report
  -> authorized approval
  -> staged deployment
  -> monitoring and rollback
```

Track data lineage, code/config version, feature schema, metrics, calibration, thresholds, and artifact checksum. Require a minimum verified batch or explicit operator action. Never train one sample at a time, never include unverified pseudo-labels by default, never evaluate on training data, and never auto-promote a candidate.

Add drift-monitoring interfaces for input quality, missingness, class distribution, calibration/outcomes, and regional performance. Supply local artifact storage and a simple model registry table if a full registry is unnecessary.

Exit gate: a demo command builds a candidate from verified synthetic records, produces a comparison report, refuses a regressing model, and requires manual promotion.

### Stage 13 — Reliability, security, accessibility, and performance

Complete threat modeling and test:

- authentication and authorization;
- object/media access controls;
- injection, unsafe file uploads, schema abuse, and rate limits;
- PII/log redaction and audit integrity;
- backup/restore documentation;
- idempotency and retry behavior;
- partial ML/provider failures;
- stale/offline conflicts;
- low-end/mobile layouts and accessibility;
- localization overflow and font rendering;
- realistic dataset/map volume.

Add health/readiness checks, structured metrics, error boundaries, correlation IDs, job status, and admin-visible degraded-component status.

Exit gate: all automated suites pass and remaining clinical/security limitations are explicitly documented.

### Stage 14 — Deployment, demonstration, and handoff

Provide:

- production-oriented Docker images and local Docker Compose;
- migrations and seed/demo commands;
- `.env.example` and configuration guide;
- architecture and sequence diagrams;
- API documentation;
- database ER diagram;
- model and data cards;
- operational runbook and rollback notes;
- privacy/safety documentation;
- test report;
- a concise SIH demo script.

Seed a deterministic scenario:

1. historical baseline reports;
2. a small rise in suspected cases in Village A;
3. a live offline farmer report in nearby Village B;
4. preliminary offline red-flag guidance;
5. synchronization and multimodal triage;
6. explainable vet-queue escalation;
7. GIS hotspot-candidate update;
8. vet correction/verification;
9. verified case added to retraining staging;
10. officer dashboard reflecting suspected versus verified counts.

Exit gate: a fresh machine can follow the README to run the complete scenario, and the final validation command passes.

## 5. Required API surface

Implement and document versioned endpoints equivalent to:

```text
POST   /api/v1/auth/dev-login
GET    /api/v1/me

POST   /api/v1/farms
POST   /api/v1/animals
GET    /api/v1/animals/{id}
POST   /api/v1/animals/{id}/vaccinations

POST   /api/v1/reports
GET    /api/v1/reports/{id}
POST   /api/v1/sync/batch
POST   /api/v1/media/presign-or-upload
GET    /api/v1/reports/{id}/timeline

POST   /api/v1/reports/{id}/triage
GET    /api/v1/reports/{id}/risk-assessment
GET    /api/v1/vet/cases
POST   /api/v1/vet/cases/{id}/assign
POST   /api/v1/vet/cases/{id}/review
POST   /api/v1/vet/cases/{id}/lab-referral
POST   /api/v1/lab-referrals/{id}/result

GET    /api/v1/gis/cases
GET    /api/v1/gis/aggregates
GET    /api/v1/gis/hotspots
POST   /api/v1/hotspots/{id}/acknowledge

GET    /api/v1/admin/model-versions
GET    /api/v1/admin/retraining-candidates
POST   /api/v1/admin/dataset-versions
POST   /api/v1/admin/model-versions/{id}/approve
POST   /api/v1/admin/model-versions/{id}/promote
```

Use pagination, validation, authorization, idempotency, consistent error envelopes, and OpenAPI examples. Modify endpoint names when existing repository conventions require it, but preserve the capabilities.

## 6. Critical domain invariants

Enforce these in code and tests:

1. AI prediction is never stored as confirmed diagnosis.
2. Suspected, vet-verified, and lab-confirmed states are distinct.
3. Only authorized veterinary/lab outcomes can become ground-truth candidates.
4. Missing modalities never crash triage and never silently imply low risk.
5. Every assessment stores feature schema, model/rule version, threshold configuration, and decision trace.
6. Emergency rule overrides cannot be suppressed by a lower model score.
7. Model uncertainty and poor image quality are visible to users.
8. Sync retries do not create duplicate reports or alerts.
9. Device time and server-receipt time are preserved separately.
10. A new model cannot reach production without evaluation and explicit approval.
11. GIS aggregation never presents suspected clusters as confirmed outbreaks.
12. Development notifications never contact real recipients.

## 7. Test matrix

At minimum, automate:

- unit tests for validation, risk thresholds, rule precedence, missingness, state transitions, spatial calculations, advisory selection, and explanation formatting;
- repository/integration tests with PostgreSQL/PostGIS;
- API authorization tests for all roles;
- contract tests for NLP, vision, weather, storage, and notification adapters;
- ML reproducibility, leakage, calibration, and regression tests;
- end-to-end farmer offline submission -> sync -> triage -> vet review -> GIS update;
- end-to-end inconclusive and lab-confirmation branches;
- duplicate sync, duplicate media, failed job, provider timeout, and stale-client tests;
- accessibility smoke tests and Marathi/Hindi rendering tests;
- load tests for map aggregation and batch synchronization.

Create one root validation command that runs formatting checks, linting, type checking, unit/integration tests, and a compact end-to-end smoke test.

## 8. Definition of done

The project is complete only when:

- the core workflow works without external paid credentials;
- offline reporting and idempotent synchronization are demonstrated;
- triage combines rules and a versioned model/stub without unsafe claims;
- probability vectors and missingness are preserved through late fusion;
- the vet can verify/correct a case and produce retraining candidates;
- the GIS dashboard distinguishes suspected, verified, and confirmed data;
- alerts/referrals have auditable state;
- model evaluation and manual promotion are implemented or faithfully simulated with clear boundaries;
- tests and local startup are reproducible;
- documentation clearly separates working features, demo adapters, future integrations, and clinical-validation requirements.

## 9. Final response expected from you

When finished, report:

1. what was built and what remains a demo adapter;
2. architecture and key design decisions;
3. stage-by-stage completion status;
4. exact startup, seed, training, and test commands;
5. test/evaluation results with no invented metrics;
6. security, privacy, offline, and clinical-safety limitations;
7. paths to the README, diagrams, model cards, API docs, and demo script;
8. the safest next steps for veterinarian validation and a field pilot.

Begin now by inspecting the repository and creating the implementation plan. Then execute Stage 0 through Stage 14, validating each stage before proceeding. Do not stop at architecture diagrams or UI mockups; deliver the integrated, tested workflow.

