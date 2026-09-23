# Operations and release checklist

## Deployment modes

With `DATABASE_URL` absent, Rolecraft is a read-only fictional demo with SQLite/FTS5 and local concept vectors. With it present, live mode is selected. Readiness needs a migrated database, `APP_ACCESS_TOKEN`, an embedding key for semantic queries, and indexed sources. `/api/status` exposes configuration flags only, not provider health. `/api/health` is process liveness only. Do not report a deployment live until its URL, final Git commit, API behavior and source mode have been verified.

## Release verification

Run all unit/API/provider tests; provision a disposable pgvector database for the integration suite; run real HTTP browser tests in Chromium, Firefox and WebKit. Tests mock paid providers, so separately verify one real authorized ingestion/search in a private preview before enabling a live workspace. Compare the candidate constraints and quote excerpts with the source. Run the authored regression evaluator, then record a baseline using a real labelled dataset before tuning retrieval.

After deploying, confirm root page/static assets, `/api/health`, `/api/status`, a representative search, zero-result behavior, saved-role lookup, mobile layout and error handling. Check runtime errors and 5xx rates. A `READY` deployment alone does not prove the database/provider integrations work. Keep previous deployment IDs and database backups for rollback. Schema changes require a backwards-compatible migration plan; `001_init.sql` is an idempotent initial schema, not a general-purpose schema drift manager.

## Imports, freshness and failures

Imports use stable source IDs and atomic indexing. Embedding calls complete before database writes; the same source is serialized with a PostgreSQL advisory transaction lock. Retry failed batches rather than the entire board. A frontend timeout means completion is unknown, not necessarily failed; inspect indexed rows before repeating. Repeating an import is idempotent for its source IDs.

Only complete small-board snapshots close missing rows immediately. Large boards are fetched in bounded batches; their contents can change between requests. Stale rows are excluded after `SOURCE_FRESH_DAYS` (14 by default), and expired/closed rows do not enter retrieval. This is not instantaneous vacancy closure detection. Use the durable `/operations` queue and separate `python -m rolecraft.worker` process for stable snapshots of up to 200 jobs. Larger sources need a new bounded adapter; they fail rather than truncate. See [the import runbook](RELIABLE_IMPORTS.md). Do not run an unbounded crawler inside a web request. Respect the source's collection and reuse requirements.

## Costs and scale

The demo makes no paid requests. Live searches may call embeddings and optionally Cohere. Briefs perform their own retrieval and optionally one chat completion. Each has a separate persisted daily request budget; it is not an exact token/dollar budget. Imports additionally cap requests at 50/day, 10 jobs per request, 48 chunks per job, 64 texts per embedding call, and character lengths. Configure provider-side spending limits too.

Exact cosine scoring after SQL filtering is intentional for correctness on modest corpora. It can be expensive on large eligible sets. The schema includes HNSW, but the default query should not be called an ANN query. Profile p95 query time, filtered recall, embedding throughput, database connections and index growth. For larger workloads, evaluate iterative filtered HNSW, partitioning, vector-store alternatives and re-ranking windows. Changing the embedding model requires a matching dimension/model schema migration and complete re-embedding; do not mix model spaces.

## Local diagnosis

`python scripts/manage.py status` tests the active store. In live mode use a pooled TLS `DATABASE_URL` appropriate for the provider. A 401 means invalid access; 503 with the configuration message means missing/too-short token; backend 503 indicates unavailable database/storage; provider 502 indicates an upstream request/validation failure; 429 indicates the persisted daily budget. Error messages intentionally omit credentials, raw queries and upstream bodies.

## Initial source delivery

Initial connector-based publication used a temporary checksum-verified, source-only transport. The release workflow validated 90 backend tests, real PostgreSQL/pgvector contracts, and nine browser scenarios in each of Chromium, Firefox and WebKit before publishing the normal source files at commit `afec1114674979ad7322124b81d6a2c9d8882237`. It used a fast-forward push, never a force-push. The transport bundle and its one-time write-enabled workflow were then removed. Normal development edits source files and uses `.github/workflows/ci.yml`, which has read-only repository permissions. Provider credentials and a verified Vercel deployment are separate from source publication.

## Version 1.1

Apply all numbered migrations with `python scripts/manage.py migrate` before upgrading the web and worker. The new `/api/readiness` endpoint separates configured storage readiness from liveness and paid-provider health. See [durable import operations](RELIABLE_IMPORTS.md) for fencing, cancellation, budgets, snapshot retention and rollback.


## Release 1.2: opt-in source scheduling

Apply `003_schedules.sql` before upgrading. New schedules start paused in the interface; the worker separately requires `IMPORT_SCHEDULER_ENABLED=true`. Source freshness diagnostics, revision-checked operator controls, atomic shared-queue admission, budget deferral and rollback instructions are in [SCHEDULED_SOURCES.md](SCHEDULED_SOURCES.md). Schedule pause/removal does not cancel admitted work or delete indexed roles.
