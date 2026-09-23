# Changelog

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
