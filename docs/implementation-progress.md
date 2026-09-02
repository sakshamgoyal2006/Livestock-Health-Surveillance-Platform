# Implementation progress — Checkpoint 1 (Stages 0–4)

Date: 2026-09-01 (Asia/Calcutta)

## Repository audit

The workspace initially contained only:

- `SIH_26128_master_execution_prompt.md` (authoritative specification);
- `SIH_26128_checkpoint_execution_prompts.md` (checkpoint-control guidance).

There were no source files, dependency manifests, tests, environment files, `.git`
directory, or nested project instructions. `git` was also absent from `PATH`, so no
working-tree status or commits were possible. No existing user code was overwritten.

Initial runtime discovery found no Node.js, npm, Python, Docker, Compose, PostgreSQL
client/server, WSL, Podman, browser, or Git. To exhaust safe alternatives for static
and unit validation, checksum-verified official Node.js 22.23.2 and Python 3.12.10
were installed only under ignored `.tools/`. They are not project dependencies or
committed artifacts. Docker Desktop was installed later and all database/browser exit
gates were subsequently exercised against an isolated Compose project.

## Stage 0 — scope and safety

Status: implemented; documentation exit gate PASS.

Created product requirements, problem/outcome traceability, clinical-safety boundaries,
architecture/sequence diagrams, acceptance criteria, privacy/location behavior, and
measurable success metrics. Clinical accuracy, false-negative, calibration, alert,
and field-operations targets are explicitly “requires domain validation.”

The demo scope is cattle/buffalo and guided observation collection. Four offline
highlight checks are explicitly unvalidated demonstration wording; they never produce
a diagnosis, low-risk decision, emergency classification, or external dispatch.

## Stage 1 — repository, infrastructure, and contracts

Status: implemented; exit gate PASS.

- npm workspace monorepo, Dockerfiles, Compose, CI, one-command startup/validation,
  environment example, structured request logs, request IDs, redaction, liveness,
  PostGIS readiness, API docs, and synthetic seed command.
- FastAPI OpenAPI is canonical. `packages/contracts/openapi.json` is generated from
  the app and TypeScript runtime-facing contracts live in `packages/contracts/src`.
- Web production build and OpenAPI generation pass locally.
- Compose declares health-gated `db -> api -> web` startup with
  `postgis/postgis:17-3.6-alpine`.

## Stage 2 — domain, PostGIS, privacy, and audit

Status: implemented; database exit gate PASS.

- SQLAlchemy metadata and initial Alembic migration cover identity, registry, raw
  observations, mortality, media, history, features/models, human/lab truth,
  advisories/outbox, spatial context/aggregates, learning governance, sync, audit,
  consent, and retention hooks.
- Farm/report/weather points use `GEOGRAPHY(Point,4326)` with GiST indexes; boundaries
  use `Geography(MultiPolygon,4326)`.
- Stable clinical fields are typed; JSONB is bounded to flexible/versioned payloads.
- Client mutation/idempotency uniqueness, request hashes, device/server timestamps,
  optimistic versions, mandatory consent, nullable optional modalities, role scope,
  safe audit details, and hash chaining are implemented.
- Optional images are compressed/chunked client-side, checksum/type/size validated,
  EXIF stripped, development-stored after the base report, and access controlled.

## Stage 3 — identity and role shells

Status: implemented; database-backed authorization exit gate PASS.

The development adapter accepts only five seeded synthetic email/role pairs and the
local password when enabled, then issues signed, expiring tokens. API authorization is
enforced independently of UI route guards. Farmer/field, veterinarian, officer, and
admin navigation/shells exist. The queue and audit viewer call live APIs; later-stage
GIS/model/lab behavior is clearly absent rather than mocked.

The five-role dependency unit matrix and 20-case PostgreSQL/PostGIS integration suite
pass. Coverage includes login/me, registry writes, vet queue, admin audit, object/media
access, invalid input, missing optional fields, duplicate retry, stale update, PostGIS,
and readiness.

## Stage 4 — offline reporting and synchronization

Status: implemented; browser/database E2E exit gate PASS.

- English/Marathi/Hindi guided labels and localized safety wording.
- Service-worker shell/questionnaire cache.
- IndexedDB drafts, mutations, registry reference data, and media outbox.
- Client UUID/idempotency key, visible state, crash-recoverable sync lease, exponential retry, resumable media,
  batch endpoint, request-hash duplicate detection, optimistic conflict, and preserved
  timestamps/consent.
- Server writes report, observations, mortality, consent, status, sync ledger, and
  audit in one transaction. Optional service/media work is outside that transaction.
- The authored Playwright test disables connectivity, submits two reports, restores
  connectivity, replays the batch, requires two `DUPLICATE` results, and checks one row
  per report in the veterinarian queue.

## Actual validation evidence

Commands below were run from the paths shown. A command is PASS only when it completed
with exit code 0.

| Area | Command | Result |
|---|---|---|
| Clean JavaScript install | `npm ci` | PASS — 435 packages installed from lockfile, 439 audited |
| JavaScript dependency audit | `npm audit --audit-level=high` | PASS — 0 vulnerabilities |
| Frontend format | `npm --workspace apps/web run format:check` | PASS — all matched files |
| Frontend lint | `npm --workspace apps/web run lint` | PASS — 0 errors/warnings |
| Frontend types | `npm --workspace apps/web run typecheck` | PASS |
| E2E TypeScript | `npm --workspace tests/e2e run typecheck` | PASS |
| Frontend unit | `npm --workspace apps/web run test` | PASS — 2 files, 7 tests |
| Production build | `npm --workspace apps/web run build` | PASS — 9 application routes plus not-found generated |
| Backend format | `python -m ruff format --check .` in `services/api` | PASS — 41 files |
| Backend lint | `python -m ruff check .` in `services/api` | PASS |
| Backend static types | `python -m mypy app` in `services/api` | PASS — 32 files |
| Backend unit/schema/API | `python -m pytest -m "not integration"` | PASS — 20 passed, 20 deselected |
| OpenAPI | `python -m scripts.export_openapi ../../packages/contracts/openapi.json` | PASS |
| Playwright discovery | `npm --workspace tests/e2e run test -- --list` | PASS — 1 test in 1 file discovered; this is not an E2E pass |
| Fresh migration | `docker compose --project-name sih-26128-validation run --rm api alembic upgrade head` (twice) | PASS — fresh PostGIS 17/3.6 volume; second run idempotent |
| Synthetic seed | `docker compose --project-name sih-26128-validation run --rm api python -m scripts.seed` (twice) | PASS — 5 explicitly synthetic identities; second run idempotent |
| API integration | `docker compose --project-name sih-26128-validation run --rm api pytest -m integration` | PASS — 20 passed, 20 deselected |
| Docker/Compose | isolated `db -> api -> web` startup on ports 15432/18000/13000 | PASS — health-gated services became healthy |
| Checkpoint browser E2E | `npm --workspace tests/e2e run test` against isolated Compose | PASS — 1/1; two offline reports synchronized exactly once and appeared once each in the vet queue |
| Git state | `git status --short --branch` | BLOCKED — no `.git` directory and `git` command absent |

The validation runs also found and repaired: invalid `.test` email validation,
missing Vitest alias resolution, overly broad lint invocation, unformatted source,
an E2E `selectOption` typing issue, an expired sync-lease recovery gap, and dependency
advisories resolved by the stable Next.js 16.3.4 update. Only final green runs count above.

## Current acceptance status

| Criterion | Status | Evidence/gap |
|---|---|---|
| Stage 0 traceability and safety boundaries | PASS | Documents and unit safety wording tests |
| Monorepo/contracts/health/build | PASS | Static/unit/OpenAPI/build evidence |
| Fresh PostGIS migration, seed, readiness, spatial query | PASS | Fresh isolated volume; migration/seed idempotency and integration assertions passed |
| Five-role authorization in unit dependency matrix | PASS | 5 parameterized unit cases |
| Five-role authorization against persisted identities/data | PASS | PostgreSQL integration role matrix passed |
| Guided multilingual form and optional failure semantics compile | PASS | Typecheck/build plus schema/unit tests |
| Durable UUID/idempotency IndexedDB queue | PASS | 5 offline queue tests, including expired and interrupted active-lease replay |
| Two-report offline browser recovery and server exactly-once | PASS | Playwright 1/1 plus duplicate-retry integration assertions |
| Veterinarian sees two synchronized reports without duplicates | PASS | Playwright verified one queue row for each report |
| PostgreSQL consent/location/times/sync/audit correctness | PASS | Database integration assertions passed |

## Known limitations and demo adapters

- Development authentication is not production identity. Tokens are stored in browser
  local storage for the local demo; production requires OIDC/HTTPS and hardened token
  handling.
- Image storage uses PostgreSQL bytes only as a deterministic development adapter.
  Production requires authorized object storage, malware scanning, quotas, and a
  retention process.
- Voice, NLP, weather, and ML adapters report unavailable. No risk model, disease
  probability, clinical rule set, verified review workflow, GIS outbreak logic, alert,
  or training lifecycle is implemented; those belong to later checkpoints.
- Translation strings require native-speaker and veterinary review.
- `npm ci` emits upstream deprecation notices for ESLint 9 and `whatwg-encoding`;
  the current Next.js plugin graph is not fully ESLint 10 compatible. `npm audit`
  reports zero vulnerabilities.
- Hash-chained audits are tamper-evident inside the database, not externally immutable.
- Browser validation uses local Chromium and development adapters; cross-browser and
  production deployment testing remain future work.

## Checkpoint boundary

Checkpoint 1 is complete. The repository is **safe to continue to Checkpoint 2 / Stage
5**, while retaining the clinical and demo-adapter limitations above. Repeat validation
with `npm run validate` or
`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate.ps1`.

# Checkpoint 2 — Stages 5–8

Status: implemented and validated on 2026-09-01. No Stage 9 veterinarian verification,
GIS outbreak workflow, alerting, or MLOps behavior was added.

## Stage 5 — versioned rules and baseline triage

- `rules-demo-1.0.0` and `thresholds-demo-1.0.0` are strict, versioned JSON configs.
  Every bundled rule has explicit `DEMO_UNVALIDATED` provenance/review metadata.
- Rules run first; emergency matches override model probabilities. Boundary and
  multi-match precedence are table tested.
- A report sync creates a durable, retryable job keyed by report UUID, pipeline
  version, and canonical input fingerprint. Completed retries return the same risk
  assessment and adding completed media creates one new versioned assessment.
- Base report durability is independent of optional analysis success.

## Stage 6 — multilingual NLP and speech boundary

- Strict English, Marathi, Hindi, and Romanized deterministic extraction covers
  entities, negation, duration, severity, source spans, ambiguity, confidence, and
  malformed provider output.
- Transcript-entry speech is a credential-free local adapter. It is not acoustic
  speech recognition and remains optional.
- Guided symptoms stay primary; NLP contradictions increase review need rather than
  overwriting guided answers.

## Stage 7 — vision probability-vector pipeline

- JPEG/PNG type, byte size, safe decoding, decompression limits, checksum, EXIF
  removal, authorization, resolution, blur, and exposure gates are enforced.
- The deterministic demo adapter returns the complete fixed five-class vector,
  quality, uncertainty, version, and explicit `OTHER_UNKNOWN` behavior.
- Rejected/absent/outage image states remain missing and do not prevent report sync.
- An authorized-image manifest contract, validator, and reproducible EfficientNet
  candidate script exist. No weights were trained because no authorized image dataset
  is present.

## Stage 8 — versioned fusion, risk, and explanations

- `triage-features-v1.0.0` combines guided clinical values, NLP, CV, prior animal
  history, vaccination records, prior weather, prior nearby PostGIS context, and
  explicit per-modality missingness. Vet review, lab/verified truth, future outcome,
  and post-triage action fields are leakage-excluded.
- The interpretable deterministic baseline returns separate suspected-condition
  likelihoods and urgency probabilities/tiers, uncertainty, insufficiency, versions,
  rule matches, override state, non-causal feature contributions, and ordered trace.
- Insufficient/conflicting input and model outage route to `VET_REVIEW`. The demo
  emergency probability threshold is 0.35 and explicitly unvalidated.
- A governed group-aware/time-ordered, class-weighted tree candidate training script
  with a separate calibration group is supplied but not trained without authorized
  clinical data.

## Checkpoint 2 actual validation evidence

Only exit-code-zero executions below are marked PASS. An earlier full run stopped at
six strict mypy findings from the container's newer dependency resolution; those were
fixed without suppressions and the complete clean run was rerun successfully.

| Area | Command | Result |
|---|---|---|
| Compact CP1 database smoke | isolated migration/seed then `pytest -q -m integration -k 'every_role_can_authenticate_and_read_me or two_reports_sync_exactly_once'` | PASS — 6 passed |
| Compact CP1 offline queue smoke | `npm --workspace apps/web run test -- tests/offline.test.ts` | PASS — 5 passed |
| Fresh migrations | `alembic upgrade head` twice in clean PostGIS volume | PASS — revisions 0001 and 0002; second run idempotent |
| Synthetic seed | `python -m scripts.seed` twice | PASS — 5 explicitly synthetic identities; idempotent |
| Backend format/lint/types | `ruff format --check .`; `ruff check .`; `mypy app` | PASS — 53 formatted files; lint clean; 41 typed modules |
| Backend unit/contracts | `pytest -m "not integration"` | PASS — 47 passed, 23 deselected |
| PostgreSQL/PostGIS integration | `pytest -m integration` | PASS — 23 passed, 47 deselected (20 CP1 regression + 3 CP2) |
| ML tooling format/lint/compile | `ruff format --check ml`; `ruff check ml`; `py_compile` for five scripts | PASS — 9 files formatted/lint clean; scripts compile |
| Reproducible demo evaluation | `python ml/risk/train_demo.py`; `python ml/risk/evaluate_demo.py` | PASS — artifact/report reproduced from 24 synthetic rows |
| JavaScript clean install/audit | `npm ci` | PASS — 435 packages installed, 439 audited, 0 vulnerabilities; non-fatal Windows cleanup warning recorded |
| Frontend format/lint/types | workspace Prettier, ESLint, web TypeScript, E2E TypeScript | PASS |
| Frontend unit | `npm --workspace apps/web run test` | PASS — 2 files, 7 tests |
| Production web build | Docker `next build` | PASS — all application routes generated |
| OpenAPI export | `python -m scripts.export_openapi ../../packages/contracts/openapi.json` | PASS |
| Browser offline + triage E2E | `npm --workspace tests/e2e run test` against clean Compose | PASS — 1/1; two offline reports exactly once plus rule override/versions/safety wording in vet UI |
| README startup path | clean isolated Compose build/start with health-gated PostGIS/API/web | PASS |
| Git status/diff | `git status --short --branch`; `git diff` | BLOCKED — this folder has no `.git` metadata and the `git` executable is absent |

## Synthetic demo evaluation (not clinical validation)

The authored dataset has 24 explicitly `SYNTHETIC_DEMO` rows. FARM_G and FARM_H form
a group-disjoint held-out set of six rows dated 2026-03-01 through 2026-03-12.

- LOW: precision/recall/F1 `1.0 / 1.0 / 1.0` (2 held-out examples).
- VET_REVIEW: `0.666667 / 1.0 / 0.8` (2 examples).
- EMERGENCY: `1.0 / 0.5 / 0.666667` (2 examples).
- Emergency sensitivity `0.5`; false-negative rate `0.5`; multiclass Brier `0.462228`.
- At demo threshold 0.35: precision `1.0`, recall `0.5`, one false negative.
- Calibration bins were not estimated because the test set is too small. Oversampling
  was not used. These values are reproducibility evidence only, not accuracy claims.

## Checkpoint 2 acceptance

| Criterion | Status | Evidence/gap |
|---|---|---|
| Sync triggers retryable/idempotent triage | PASS | durable job/fingerprint plus integration retry/count assertions |
| Reviewed/demo-labelled red flags run first and override | PASS | versioned provenance and precedence/override unit + integration + E2E |
| Guided symptoms are trusted primary input | PASS | fusion contract and conflict test |
| English/Marathi/Hindi/Romanized strict NLP | PASS | native, Romanized, negation, ambiguity, malformed response fixtures |
| Optional credential-free speech boundary | PASS | transcript-entry demo adapter and test |
| Image security and quality gates | PASS | MIME/size/decode/resolution/blur/exposure tests |
| Complete ordered CV vector/unknown/outage behavior | PASS | strict contract, class-order, sum, unknown, outage tests |
| Versioned multimodal/context feature builder | PASS | persisted snapshot integration and modality-combination tests |
| Missing modalities remain null with indicators | PASS | form/text/image/no-weather/partial-history coverage |
| Three-tier calibrated or demo-labelled risk | PASS | `DEMO_UNVALIDATED` response/config and threshold report |
| Suspected condition likelihood separate from urgency | PASS | API contract, persisted assessment, and UI |
| Careful explanation, uncertainty, versions, trace | PASS | API integration and browser assertions; no diagnosis wording |
| Real model training/clinical validation | BLOCKED | no authorized clinical/tabular/image dataset; no accuracy claim |

## Checkpoint boundary

Checkpoint 2 is complete and the repository is **technically safe to continue to
Checkpoint 3**, provided all outputs remain preliminary demo decision support until
authorized data, veterinary review, calibration, and clinical validation exist.

# Checkpoint 3 — Stages 9–12

Status: implemented on 2026-09-03. Validation evidence below records only commands that
actually returned exit code zero. Stage 13 and later hardening were not implemented.

## Operational workflow

- Every completed triage idempotently creates one versioned veterinary case and keeps
  the original preliminary prediction immutable. Veterinarian evidence includes raw
  observations, media metadata, NLP/CV quality/uncertainty, rules/models/features,
  condition and urgency probabilities, explanations, decision trace, nearby PostGIS
  cases, cached weather, review history, lab history, and follow-ups.
- The guarded state machine supports assignment, review, confirm/correct/inconclusive,
  sample request, lab pending/result, follow-up, escalation, and close paths. Expected
  versions reject stale writes. Suspected, vet-verified, and lab-confirmed truth remains
  separate in storage, APIs, and the district UI.
- PostGIS point context stays veterinarian-only. Officer APIs provide rounded or
  suppressed aggregates. `rolling-baseline-demo-1.0.0` combines a two-day window,
  14-day baseline, ten-kilometre proximity, minimum count, lift, and verification
  confidence. Outputs are hotspot candidates only.
- The chronological seed is explicitly synthetic: Village A/B baseline, Village A Day
  1 small signal, Village A Day 2 rise plus a nearby Village B report. The browser E2E
  adds an offline Village B report and verifies the independent map layers after review.
- Advisory templates are available in English, Marathi, and Hindi. The development
  outbox implements event/delivery deduplication, retries, rate limiting,
  acknowledgement, escalation, and `external_send: false` receipts.
- Only authorized vet/lab records can stage training candidates. Quality review,
  deduplication, immutable batch manifests, locked-benchmark comparisons, regression
  rejection, explicit administrator approval, promotion, and rollback are implemented.
  No unverified prediction is a label and nothing auto-deploys.

## Validation evidence

| Area | Command | Result |
|---|---|---|
| Initial CP1–2 regression smoke | isolated PostGIS plus focused integration and offline queue tests | PASS — 8 backend smoke assertions and 5 offline tests |
| Fresh migration | `alembic upgrade head` from an empty PostGIS volume, then repeated | PASS — revisions 0001–0003; second invocation no-op |
| Synthetic seed | `python -m scripts.seed`; `python -m scripts.seed_checkpoint3` | PASS — five identities, Village A/B chronology, cached weather, demo model, one hotspot candidate |
| Backend format/lint/types | `ruff format --check .`; `ruff check .`; `mypy app scripts` | PASS |
| Backend unit/contracts | `pytest -m "not integration"` | PASS — 51 passed, 28 deselected |
| PostgreSQL/PostGIS integration regression | `pytest -m integration` | PASS — 28 passed, 51 deselected (20 CP1, 3 CP2, 5 CP3) |
| Frontend format/lint/types | Prettier, ESLint, web and E2E TypeScript | PASS |
| Locked synthetic benchmark | `python services/api/scripts/evaluate_checkpoint3_candidate.py` | PASS — reproducible report; metrics below |
| Frontend unit | `npm --workspace apps/web run test` | PASS — 2 files, 7 tests |
| Production web build | Docker `next build` | PASS — 13 routes generated, including all CP3 screens |
| Browser CP1–3 E2E | `npm --workspace tests/e2e run test` | PASS — 2/2 serial stateful scenarios |
| Full clean command | `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate.ps1` | PASS — completed and removed isolated services/volume |

## Synthetic locked-benchmark report (not clinical performance)

The immutable fixture contains six explicitly synthetic, temporally ordered examples
from two identity groups. The current deterministic baseline produced 5/6 correct,
emergency sensitivity 0.5, and multiclass Brier 0.462228. The intentional regression
fixture produced 2/6 correct, emergency sensitivity 0.0, and Brier 1.293933 and is
rejected. Calibration status is `DEMO_UNVALIDATED`; these values are reproducibility
and safety-gate evidence only.

## Checkpoint 3 current acceptance

| Criterion | Status | Evidence/gap |
|---|---|---|
| Authorized auditable case state machine | PASS | integration state, stale, role, and timeline assertions |
| Complete vet evidence and action branches | PASS | API/UI plus corrected, inconclusive, sample/lab, follow-up, escalation tests |
| Suspected/vet/lab status separation | PASS | schema, case evidence, aggregate counts, and UI layers |
| Authorized verified-only retraining provenance | PASS | provenance and pseudo-label rejection tests |
| Immutable original prediction vs ground truth | PASS | immutable reference and evidence assertions |
| PostGIS point context and privacy aggregates | PASS | proximity/aggregate integration and role denial |
| Temporal/proximity hotspot candidate detection | PASS | chronological seed plus baseline/minimum/lift/confidence assertions |
| Optional cached weather | PASS | missing/available adapter paths exposed in vet evidence |
| Marathi/Hindi/English template advisories | PASS | table-driven contract and farmer-scoped API |
| Alert outbox lifecycle and no-send adapter | PASS | dedup/retry/rate-limit/ack/escalation/external-send assertions |
| Lab referral/result authoritative truth | PASS | sample-request, lab-pending, and lab-confirmed integration paths |
| Verified batch/evaluate/reject/approve/promote/rollback | PASS | database/API lifecycle test and locked report |
| Clinical or field validation | BLOCKED | no authorized clinical dataset, field study, or reviewed clinical thresholds |

## Checkpoint boundary

Checkpoint 3 is complete and the repository is **technically safe to continue to final
hardening**, while remaining explicitly unsuitable for field or clinical use. Final
hardening must not reinterpret the demo rules, advisories, detector, benchmark, or
probabilities as validated clinical behavior.
