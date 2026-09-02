# Checkpoint 3 operational and governance contracts

Everything in this checkpoint remains prototype decision support. The clinical rules,
advisories, risk outputs, detector thresholds, and benchmark are demo-labelled and are
not clinically or field validated.

## Veterinary case state and truth separation

Triage creates exactly one `veterinary_cases` row for a report and stores the first
`risk_assessment_id` as the immutable original prediction. The prediction is never
rewritten by a review or lab result.

Allowed case transitions are:

```text
TRIAGED -> ASSIGNED -> UNDER_REVIEW
UNDER_REVIEW -> VET_VERIFIED | INCONCLUSIVE | SAMPLE_REQUESTED
SAMPLE_REQUESTED -> LAB_PENDING | INCONCLUSIVE
LAB_PENDING -> LAB_CONFIRMED | LAB_NEGATIVE | INCONCLUSIVE
VET_VERIFIED -> CLOSED | SAMPLE_REQUESTED
LAB_NEGATIVE -> VET_VERIFIED | INCONCLUSIVE | CLOSED
INCONCLUSIVE -> UNDER_REVIEW | CLOSED
LAB_CONFIRMED -> CLOSED
```

Every write uses an expected case version and appends status/audit history. A
veterinarian may self-assign and then review only their assigned case; an administrator
may assign/audit but cannot create a veterinary verification label. `suspected_status`,
`verified_status`, and `lab_status` are separate fields and separate dashboard counts.

## GIS and hotspot candidates

Individual point/nearby context is returned only inside the veterinarian case evidence
API. District officers receive village/block/district aggregates with coordinates
suppressed below two records and rounded otherwise.

The deterministic `rolling-baseline-demo-1.0.0` detector requires all of:

- reports in a two-day time window;
- the largest ten-kilometre proximity cluster within a village;
- at least three reports;
- at least two times the expected count from the preceding 14-day baseline; and
- a confidence score that includes the proportion of authorized verified cases.

Its output is always `CANDIDATE` or `ACKNOWLEDGED_CANDIDATE`, never “confirmed
outbreak.” Cached database weather is optional and a missing observation stays missing.

## Advisories and alerts

`advisories.v1.json` contains English, Marathi, and Hindi templates for each urgency
tier. They are marked `DEMO_UNVALIDATED` and do not name a confirmed diagnosis.

Alerts use an event plus transactional outbox. Event and delivery deduplication keys
are unique. The outbox enforces bounded retries, exponential retry times, a per-recipient
rate limit, acknowledgement, and escalation after permanent failure. The only bundled
adapter is `DevelopmentNoSendAdapter`; it records `external_send: false` and never
contacts a real recipient.

## Verified active learning

Only an authorized `VetReview` or `LabResult` may stage a retraining candidate.
Prediction-derived sources are rejected. Each row stores source-record provenance,
raw-report version, feature schema, deduplication hash, immutable checksum, and quality
review status.

Approved candidates are built in batches into a locked dataset manifest. Batches below
ten are allowed only by an explicit synthetic-demo flag and only when every reporter is
marked synthetic. The locked synthetic benchmark is excluded from training. Candidate
metadata includes dataset, benchmark, code, feature schema, threshold, artifact
checksum, and regression results. Promotion requires a separate administrator approval
record; rejected regressions cannot be promoted; no path auto-promotes; rollback
restores the prior active version.
