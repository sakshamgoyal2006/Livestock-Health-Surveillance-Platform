# Clinical safety boundaries

## Status of this software

This is an unvalidated triage-support prototype. Reporter input is an observation,
not a diagnosis. A synchronized report remains `QUEUED_FOR_VET`; no disease label is
generated in Checkpoint 1. Veterinary or laboratory truth must remain separate from
raw observations and future model output.

## Demonstration-only offline checks

The client can highlight the following reporter selections so the user does not miss
them while offline:

- animal reported unable to stand;
- difficult breathing reported;
- one or more deaths reported;
- reporter selected severe symptoms.

These checks are **not clinician approved and not clinically validated**. They only
change the wording from routine veterinary review to prompt veterinary review. They do
not assign `LOW` or `EMERGENCY`, infer a condition, suppress any report, prescribe a
treatment, or dispatch an alert. Stage 5 must replace/configure rules only after named
clinical ownership, provenance, review metadata, effective dates, and boundary tests
exist.

## User-facing language

Permitted wording includes “reported observation,” “preliminary,” “prompt veterinary
review,” and “veterinary verification required.” The UI and API must not use
“confirmed,” “diagnosed,” “outbreak,” or “safe/low risk” for an unverified report.

The prototype does not provide emergency contact numbers because no authoritative
local directory was supplied. A real deployment must have a veterinarian-approved,
district-specific escalation path and fallback before field use.

## Optional modality failures

Image, voice, NLP, weather, and ML state is explicitly `NOT_PROVIDED`, `PENDING`, or
`UNAVAILABLE`. Absence is never converted to zero risk. These adapters cannot be in
the transaction needed to store a base report. Optional images use the local secured
upload adapter; voice, NLP, weather, and ML use unavailable development adapters.

## Consent, privacy, and access

- Consent version and device/server receipt times are stored independently.
- Exact GPS is not required. Village-only location is the default; approximate or
  exact coordinates require an explicit precision choice.
- Farmer/field-worker access is scoped to owned/assigned farms. Veterinarians can read
  the queue. Only administrators can read the audit viewer. Officer access to raw
  case points is absent at this checkpoint.
- Logs and audit details exclude report notes, voice transcripts, credentials, and
  raw authorization headers.
- Optional images are compressed on device, chunked, checksum-verified, stripped of
  EXIF on the server, and readable only by the reporter, veterinarians, or admins.
  This development adapter stores sanitized bytes in PostgreSQL and is not a
  production object-storage design.
- Retention requests are reviewable hooks; deletion is never automatic.

## Clinical ownership still required

Before a pilot, qualified Maharashtra veterinary/public-health owners must validate
questionnaire wording, escalation ownership, language translations, species scope,
syndrome definitions, red flags, advisories, response times, contact pathways, and
all accuracy/calibration targets. None is claimed here.
