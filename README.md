# SIH 26128 Livestock Health Surveillance — Checkpoint 3

This repository contains the Stage 0–12 vertical slice for a cattle and
buffalo health-reporting PWA. It is an early-warning and veterinary triage support
prototype, **not a diagnostic system**. Any offline red-flag message is explicitly
unvalidated demonstration logic and veterinary verification is required.

## What works

- Development-only signed-token login for all five roles.
- Farmer/field-worker farm, herd, and animal registration.
- A guided report form with consent, device time, location precision, optional
  coordinates, and nullable optional modalities.
- Durable IndexedDB drafts/mutation queue, service-worker shell cache, retry/backoff,
  client UUIDs, idempotency keys, and visible sync states.
- Optional on-device image compression and resumable chunk upload; the development
  server validates type/size/checksum, removes EXIF metadata, and authorizes reads.
- Atomic PostgreSQL/PostGIS batch synchronization with duplicate replay detection,
  optimistic conflict responses, and audit history.
- Retryable, input-fingerprinted triage jobs with versioned demo rules, multilingual
  NLP/speech boundaries, image quality and probability-vector processing, explicit
  missingness fusion, preliminary urgency, uncertainty, and explanations.
- A role-protected veterinarian case workflow with optimistic state transitions,
  immutable original predictions, correction/inconclusive/follow-up/escalation actions,
  and lab referral/result branches.
- PostGIS nearby context plus privacy-preserving village/block/district aggregates and
  a temporal/proximity hotspot-candidate detector that never calls density an outbreak.
- English, Marathi, and Hindi demo advisory templates and a retryable/deduplicated alert
  outbox whose development adapter never sends to real recipients.
- Verified-only retraining staging, immutable synthetic-demo datasets, locked benchmark
  evaluation, regression rejection, manual promotion approval, and rollback.

## Prerequisites

- Docker Desktop with Compose v2.
- Node.js 20.9+ and npm (needed for local frontend checks and Playwright).

No paid service or external account is required.

## Clean start

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open <http://localhost:3000>. API documentation is at
<http://localhost:8000/docs>, liveness at <http://localhost:8000/health>, and
PostGIS-aware readiness at <http://localhost:8000/ready>.

The API container applies migrations and idempotently loads clearly labelled synthetic
development identities and the Village A/B chronological surveillance demonstration.
Example identities are shown on the login screen; the password is `dev-only`.

## Explicit database commands

```powershell
docker compose up -d db
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m scripts.seed
docker compose run --rm api python -m scripts.seed_checkpoint3
docker compose run --rm api alembic downgrade base
```

Do not run the downgrade command against data you need to retain.

## Development without rebuilding containers

API:

```powershell
cd services/api
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:DATABASE_URL="postgresql+asyncpg://sih:change-me-development-only@localhost:5432/sih"
alembic upgrade head
python -m scripts.seed
python -m scripts.seed_checkpoint3
uvicorn app.main:app --reload
```

Web, in another terminal:

```powershell
npm ci
npm --workspace apps/web run dev
```

## Tests

The full clean-database validation command is:

```powershell
npm run validate
```

If `npm` is not installed globally, run the repository script directly; it locates
the bundled Node/Python runtimes:

```powershell
cd C:\Users\goyal\OneDrive\Desktop\SIH
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate.ps1
```

Validation uses the isolated Compose project `sih-26128-validation`; its initial
volume cleanup does not remove the normal development project's database volume.

Focused commands:

```powershell
docker compose run --rm api ruff format --check .
docker compose run --rm api ruff check .
docker compose run --rm api mypy app
docker compose run --rm api pytest -m "not integration"
docker compose run --rm api pytest -m integration
npm --workspace apps/web run format:check
npm --workspace apps/web run lint
npm --workspace apps/web run typecheck
npm --workspace apps/web run test
docker compose up -d api web
npm --workspace tests/e2e run install:chromium
npm --workspace tests/e2e run test
.\.tools\python312\python.exe ml\risk\train_demo.py
.\.tools\python312\python.exe ml\risk\evaluate_demo.py
$env:PYTHONPATH="services/api"
.\.tools\python312\python.exe services\api\scripts\evaluate_checkpoint3_candidate.py
```

The Playwright suite preserves the two-report exactly-once regression scenario and adds
an offline Village B report that synchronizes, enters the veterinary state machine, is
corrected by a veterinarian, and updates the separate suspected/verified/lab GIS layers.

## Development identity boundary

The local identity adapter is enabled only when `DEV_AUTH_ENABLED=true`. It accepts
only seeded email/role pairs and the fixed local password. Tokens are signed using
`AUTH_SECRET`; production must disable this adapter and provide a real OIDC adapter.

## Project map

- `apps/web`: Next.js PWA, IndexedDB sync/media queue, and multilingual guided labels.
- `services/api`: FastAPI modular monolith, Alembic, PostGIS models, and tests.
- `packages/contracts`: shared TypeScript API and mutation contracts.
- `tests/e2e`: Playwright offline/exactly-once and Checkpoint 3 operations tests.
- `ml`: deterministic demo evaluation plus governed real-training contracts/scripts.
- `docs`: decisions, architecture, privacy/safety, pipeline contracts, acceptance
  traceability, and implementation evidence.

See `docs/implementation-progress.md` for actual validation evidence and known
environment blockers.
