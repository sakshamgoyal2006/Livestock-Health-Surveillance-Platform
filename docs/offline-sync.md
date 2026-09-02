# Offline synchronization contract

1. The client validates guided fields, records consent/device time, creates a report
   UUID, mutation UUID, and idempotency key, then commits one IndexedDB transaction.
2. UI submission success means “durably queued,” not “received by server.”
3. Pending/failed mutations retry on the browser `online` event or explicit user action.
   Backoff is exponential and capped at five minutes.
4. The server looks up either mutation UUID or idempotency key. The canonical JSON
   request hash must match a prior delivery. Matching applied work returns `DUPLICATE`;
   changed content returns `CONFLICT`.
5. First delivery writes the report, typed observations, consent, status history, sync
   ledger, and audit event in one transaction. Optional providers do not participate.
6. An update must carry `base_version`. A mismatch returns `STALE_VERSION`; the server
   record is not overwritten. UI retains the conflict for a future explicit resolution
   workflow.
7. `created_at_device` and `received_at_server` are never collapsed. Clock skew is
   bounded for future timestamps; device time is not treated as authoritative ordering.
8. `ACKED` client records remain available for local history and duplicate-replay
   evidence. A later retention policy may safely compact them after server confirmation.

Optional images are compressed to a bounded JPEG in the browser and stored in a
separate IndexedDB media outbox. After the base report is acknowledged, 512 KiB chunks
resume from the last acknowledged index. The server validates type, per-chunk/total
size, SHA-256 checksum and image decoding, removes EXIF, and applies report-based read
authorization. A media failure leaves the report `ACKED` and the image retryable.
