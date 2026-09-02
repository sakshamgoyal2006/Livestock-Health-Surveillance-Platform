# Product requirements — Checkpoint 1 baseline

## Purpose and users

Pashu Seva is an early-warning and veterinary decision-support prototype for livestock
health observations in Maharashtra. It is not an autonomous diagnostic system. The
Checkpoint 1 demo is deliberately narrow: cattle and buffalo, guided health reports,
durable offline collection, auditable synchronization, and a basic veterinary queue.

Supported roles are `FARMER`, `FIELD_WORKER`, `VETERINARIAN`, `DISTRICT_OFFICER`, and
`ADMIN`. Development identities and all seeded people are explicitly synthetic.

## Checkpoint 1 functional requirements

| ID | Requirement | Verification |
|---|---|---|
| CP1-F-01 | A seeded farmer or field worker can use the development identity adapter. | `test_every_role_can_authenticate_and_read_me`; Playwright checkpoint test |
| CP1-F-02 | A reporter can register a farm and an animal or herd. | registry API authorization/integration tests; Playwright checkpoint test |
| CP1-F-03 | The guided form captures species, age band, onset, severity, intake, mobility, respiration, visible signs, vaccination, movement/contact, mortality, location precision, consent, and timestamps. | schema unit tests and synchronized database assertions |
| CP1-F-04 | A report can be submitted with optional image, voice, NLP, weather, and ML absent or unavailable. | missing-optional schema test and integration test |
| CP1-F-05 | Offline reports survive navigation/browser process loss in IndexedDB. | frontend durable queue unit test and Playwright offline test |
| CP1-F-06 | Every offline mutation has a client UUID and idempotency key. | frontend queue unit test; database unique constraints |
| CP1-F-07 | Duplicate retries create one canonical report. | API duplicate integration test; Playwright duplicate replay |
| CP1-F-08 | Stale updates return a conflict and do not overwrite current state. | stale-update integration test |
| CP1-F-09 | A veterinarian, but not another application role, can read the basic queue. | five-role authorization matrix |
| CP1-F-10 | Device/server times, consent, sync identity/state, PostGIS location, and audit history persist. | PostGIS/consent/audit integration assertions |

## Non-functional requirements

- Mobile-first, keyboard-usable controls have a minimum 44 px target size.
- The application shell and questionnaire reference are service-worker cached.
- A batch accepts at most 50 mutations; retry delay grows exponentially to five
  minutes and is visible in local state.
- API errors are versioned JSON envelopes carrying a request ID.
- Logs do not include credentials, report notes, or voice transcripts.
- Stable searchable clinical observations use typed columns; flexible provider status
  is JSONB with an explicit bounded contract.
- Exact coordinates are optional. Village-only precision is the default.

## Traceability to the problem statement and final product

| Problem-statement outcome | Product feature | Checkpoint/test trace |
|---|---|---|
| Earlier detection of livestock health issues | Guided observations, device timestamp, durable offline reporting, veterinarian queue | CP1-F-03 through CP1-F-10; later validated triage tests are reserved for Checkpoint 2 |
| Prevention support | Safe template/advisory boundary and prompt veterinary routing | Offline wording unit test now; approved multilingual advisory tests are reserved for Checkpoint 3 |
| Management of livestock health issues | Farm/animal/herd longitudinal identifiers and auditable case records | CP1-F-02 and CP1-F-10; authoritative vet workflow tests are reserved for Checkpoint 3 |
| Accessible rural reporting | PWA shell, offline queue, village-only location, large controls | CP1-F-05, Playwright offline test, later formal accessibility audit |
| Veterinary decision support | Role-protected queue separating observation from verified truth | CP1-F-09; model/rule evidence tests are reserved for Checkpoint 2 |
| Emerging geographic risk | PostGIS storage with privacy-preserving precision | CP1-F-10; aggregate/hotspot tests are reserved for Checkpoint 3 |
| Safe learning from outcomes | Separate prediction, review, lab truth, dataset, candidate, and approval tables | schema inspection now; provenance/promotion tests are reserved for Checkpoint 3 |

## Non-goals for Checkpoint 1

- No diagnosis, disease probability, clinical threshold, validated emergency rule, or
  treatment recommendation.
- No live speech, translation provider, NLP, weather, image analysis, ML, SMS,
  WhatsApp, laboratory, map, hotspot, model training, or public-health integration.
- No automatic outbreak declaration, alert transmission, or model promotion.
- No claim of veterinarian approval, accuracy, field readiness, or government use.

