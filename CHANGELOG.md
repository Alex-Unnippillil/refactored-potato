# Changelog

## 1.3.0 — search reliability and source evidence

- Add a selected-preference source audit with supporting/conflicting/mixed/uncertain/not-found states, exact Unicode spans and transparent branch ranks. Replace broad positive culture cues with conservative explicit wording and bounded negation/hedging.
- Allow only transient embedding outages to trigger a visibly labelled hybrid-to-keyword fallback with the original filters. Explicit meaning-only and strict API requests fail instead; provider/schema/database errors remain errors.
- Keep eligible counts, retrieval and job payloads in one repeatable-read, read-only PostgreSQL snapshot. Exclude stale/expired live jobs from saved lookups and export.
- Reject malformed embedding/rerank indices, non-finite/boolean values and near-zero vectors. Preserve degradation and conflict caveats in evidence briefs.
- Add local workspace locking, request-epoch fencing and cleared private caches on token replacement; retain explicitly saved device-local presets by design.
- Extend unit, real PostgreSQL concurrency and three-browser HTTP coverage. Update the architecture, runbook and eight reproducible demo screenshots. No new schema migration or external service is provisioned.


## 1.2.0 — 2026-09-23

### Added
- Opt-in recurring Greenhouse source refreshes using the existing durable queue; no new broker or scheduler dependency.
- Paused-by-default source setup, 6–168-hour intervals, pause/resume, manual run, confirmed removal and revision-checked interval editing.
- Atomic dispatch/deadline writes, missed-interval coalescing, active-board deduplication and budget/capacity deferral.
- Per-source retrieval freshness counts, retained successful-run timestamps, shared quota diagnostics and a separate scheduler heartbeat.
- Additive `003_schedules.sql`, direct-database operator CLI, upgrade/rollback and scheduling runbook.
- Real PostgreSQL schedule/concurrency tests and private HTTP browser lifecycle/privacy tests.
- Updated architecture and reproducible demo screenshots, plus tracked-source artifacts from successful CI runs.

### Changed
- Worker scheduling is disabled unless `IMPORT_SCHEDULER_ENABLED` explicitly enables it. Existing queued imports continue even when scheduler dispatch fails.
- Operator mutations invalidate pending reads; clearing access erases private schedules and drafts and prevents late-response repopulation.
- Readiness checks the schedule schema. Demo and live provider-health limitations remain explicit.

### Deployment boundary
- GitHub test results are not a hosted deployment or real-provider smoke-test claim. Live operation still needs migrated PostgreSQL/pgvector, separate tokens, provider credentials and an externally operated worker. This remains a single private workspace, not multi-tenant SaaS.

## 1.1.0 — 2026-09-23

- Durable Greenhouse snapshots, fenced leases, cancellation, bounded retries and atomic cursor checkpoints.
- Operations dashboard, readiness checks, non-root read-only container and real-HTTP screenshot capture.
