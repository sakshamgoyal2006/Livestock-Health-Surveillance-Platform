# Checkpoint 1 database dictionary

All identifiers are UUIDs. All timestamps are timezone-aware. `created_at_device` is
reporter device time and is never substituted for `received_at_server`.

| Area | Tables | Purpose |
|---|---|---|
| Identity | `users`, `farmer_profiles`, `field_worker_profiles`, `veterinarian_profiles` | Role identity and narrow profile data; seed identities carry `synthetic=true`. |
| Registry | `farms`, `herds`, `animals`, `ownership_assignments` | Longitudinal livestock subjects and scoped farm access. |
| Raw reporting | `health_reports`, `mortality_reports`, `symptom_observations`, `consent_records` | Typed reporter observations, consent, source, device/server time, and optimistic version. |
| Media | `media_assets`, `media_upload_chunks`, `media_blobs` | Authorized resumable upload, checksum/EXIF state, and local-development sanitized bytes. |
| History | `vaccination_records`, `treatment_records`, `disease_history` | Separate longitudinal facts; disease truth status is explicit. |
| Derived/model | `feature_snapshots`, `risk_assessments`, `explanations`, `model_versions` | Versioned future features/predictions, distinct from raw observation and truth. |
| Human/lab | `vet_reviews`, `case_assignments`, `status_history`, `lab_referrals`, `lab_results` | Future authoritative decisions and traceable case transitions. |
| Response | `advisories`, `alert_events`, `notification_outbox` | Approved content and deduplicated future delivery boundary. |
| Spatial/context | `administrative_areas`, `weather_snapshots`, `surveillance_aggregates` | PostGIS areas/points and separate suspected/verified/lab aggregate counts. |
| Learning governance | `retraining_candidates`, `dataset_versions`, `promotion_approvals` | Verified-only staging, immutable provenance, and explicit human promotion approval. |
| Reliability/privacy | `sync_mutations`, `audit_logs`, `retention_requests` | Idempotency/request hashes, tamper-evident safe audit events, and reviewed retention hooks. |

`farms.location`, `health_reports.location`, and `weather_snapshots.location` use
PostGIS `GEOGRAPHY` with SRID 4326 and GiST indexes. Administrative boundaries use
`GEOGRAPHY(MultiPolygon,4326)`. Stable searchable report fields are relational columns;
JSONB is not the sole clinical store.

Important constraints include unique mutation UUID/idempotency key, unique report
mutation identities, unique farm/tag, paired and bounded coordinates at the API plus
database coordinate bounds, nonnegative mortality, bounded temperature, and mandatory
consent for a canonical health report.

