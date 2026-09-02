# Acceptance criteria and measurement plan

## Checkpoint 1 release gate

| Criterion | Evidence required | Target |
|---|---|---|
| Clean startup | README commands, health and PostGIS readiness responses | All available from a clean volume |
| Clean migration and seed | Alembic upgrade from empty PostGIS plus idempotent synthetic seed | Pass twice without duplication |
| Offline durability | Two reports inserted into IndexedDB while browser context is offline | 2 pending records with distinct UUID/idempotency keys |
| Recovery | Restore connectivity and synchronize | 2 `ACKED`, no lost report |
| Exactly once | Replay identical batch and query vet queue/database | `DUPLICATE`, one canonical row per report |
| Privacy and audit | Query report, consent, geography, sync ledger, and audit | Correct device/server times, consent version, location precision, and audit event |
| Authorization | Exercise protected routes as every role | Matrix matches policy with 401/403/2xx |
| Failure tolerance | Submit nullable optional fields and unavailable provider state | Base report is `APPLIED` |
| Invalid/stale data | Invalid consent/values and stale version update | Reject/conflict with no canonical corruption |
| Code quality | Formatting, lint, frontend types, mypy, unit, integration, and E2E | Every configured command runs and passes |

## Product success metrics

| Metric | Initial target/status |
|---|---|
| Guided report completion time | Instrument later; usability target requires field validation |
| Mutation synchronization success | ≥99% in an approved test network profile; not yet measured |
| Exactly-once recovery | 100% in automated duplicate-replay cases |
| Offline recovery after browser restart | 100% in automated durable-store cases; full device matrix not measured |
| High-risk sensitivity | Requires approved labelled clinical test set and domain validation |
| False-negative rate | Requires approved labelled clinical test set and domain validation |
| Probability calibration/Brier score | Requires approved labelled clinical test set and domain validation |
| Vet-review turnaround time | Requires operational pilot and domain validation |
| Alert precision | Requires approved alert definition, baseline data, and domain validation |
| Accessibility | Keyboard/semantic smoke now; WCAG 2.2 AA audit requires specialist validation |
| Marathi/Hindi usability | Translation and layout review requires native-speaker/domain validation |

## Exit decision

Checkpoint 2 may begin only when migration, role authorization, offline storage,
exactly-once sync, PostGIS/audit persistence, and base-report failure tolerance are
PASS. Missing local runtimes are `BLOCKED`, never inferred as passed from source code.

