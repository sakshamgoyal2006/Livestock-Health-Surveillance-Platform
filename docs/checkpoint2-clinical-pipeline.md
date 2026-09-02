# Checkpoint 2 clinical pipeline contracts

This checkpoint implements preliminary decision support, not diagnosis or clinical
validation. All bundled rules, probabilities, thresholds, NLP extraction, and image
classification behavior are explicitly deterministic demonstration implementations.

## Execution and idempotency

A successful `CREATE_REPORT` sync commits the base report first and then enqueues a
triage job keyed by `report UUID + pipeline version + canonical input fingerprint`.
Retries return the existing completed assessment; failed jobs can be retried up to
three times. Adding a completed image changes the fingerprint and creates one new,
versioned assessment. Optional adapter failures cannot roll back the base report.

Version compatibility is explicit: pipeline `triage-pipeline-1.0.0` consumes rule set
`rules-demo-1.0.0`, thresholds `thresholds-demo-1.0.0`, and feature schema
`triage-features-v1.0.0`. Persisted analysis artifacts also carry adapter/model and
input-fingerprint fields.

## Modality contracts

| Modality | Input | Output | Missing/failure behavior |
|---|---|---|---|
| Guided form | typed severity, intake, mobility, respiration, lesions, discharge, temperature, vaccination, contact/movement, mortality | trusted clinical values | mandatory primary input; never replaced by NLP/CV |
| Text NLP | up to 4,000 UTF-8 characters; `en`, `mr`, `hi`, or unknown hint | strict `SymptomExtraction`: language, entities, negation, duration, severity, body sites, spans, ambiguity, confidence, adapter version | `NOT_PROVIDED`, uncertain, or failed artifact; does not erase guided values |
| Speech | transcript-entry local adapter boundary | text passed through the same NLP contract | no paid credentials; absent audio/transcript remains absent |
| Image | JPEG/PNG, checksum, authorized report ownership | ordered five-class probability vector, image quality, uncertainty, model version, calibration status | security rejection, quality rejection, or model outage routes safely without blocking the report |
| Weather | prior database observation within 50 km | nullable temperature and humidity | null plus `weather_missing=true`, never zero risk |
| History/vaccination | pre-report animal records only | nullable counts | null plus separate missingness indicators |
| GIS context | prior reports within 10 km and seven days | nullable count | null plus `gis_context_missing=true`; no outbreak workflow is implemented |

The fixed vision class order is `SKIN_LESION`, `OCULAR_NASAL_DISCHARGE`, `SWELLING`,
`NORMAL_APPEARANCE`, `OTHER_UNKNOWN`. Every accepted prediction must contain all five
finite probabilities summing to one. Low quality increases unknown/uncertainty; a
missing or rejected image never becomes a zero-valued normal image.

## Fusion and decision contract

The feature snapshot stores three maps: nullable `values`, boolean `missingness`, and
`source_versions`. It excludes veterinary review, verified labels, lab results,
future outcomes, and post-triage action fields to prevent target leakage.

The response separates suspected syndrome/visible-condition likelihoods from urgency
probabilities for `LOW`, `VET_REVIEW`, and `EMERGENCY`, and includes final tier,
uncertainty, insufficiency, rules, override, versions, feature contributions, and an
ordered trace.

Rules execute before the demo score. Any matched emergency rule overrides model
probabilities. Missing/conflicting information normally routes to `VET_REVIEW`.
The configured `P(EMERGENCY) > 0.35` threshold is named and visibly marked
`DEMO_UNVALIDATED`; it is not a universal clinical threshold. Contributions are model
feature contributions, not causes or percentage changes.

## Implementation boundary

- Real: durable PostgreSQL/PostGIS jobs/artifacts/features/assessments/explanations,
  API authorization/idempotency/retry behavior, image security/quality gates,
  version checks, UI decision trace, and reproducible test/evaluation tooling.
- Demo: rules, multilingual lexicon NLP, transcript-entry speech, pixel-statistic CV,
  interpretable urgency scoring, suspected-condition scores, and thresholds.
- Not trained: the tree candidate and transfer-learning vision candidate. Scripts and
  governed data contracts are present, but no authorized clinical/tabular/image data
  is available. No clinical accuracy claim is made.

Veterinarian verification actions, GIS outbreak workflow, alerting, and MLOps are
outside this checkpoint and intentionally remain unimplemented.
