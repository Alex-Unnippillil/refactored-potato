# Scheduled sources — Rolecraft 1.2

Recurring refresh is an **opt-in Greenhouse Job Board API workflow**, not a general-purpose crawler or a hosted scheduler service. The same PostgreSQL import queue, snapshot validation, fenced worker and job-attempt budget serve manual and recurring imports. No additional scheduler dependency, broker, account or paid resource is provisioned.

## Enable deliberately

1. Back up the live database, then run `python scripts/manage.py migrate` with a migration-capable connection. This applies `003_schedules.sql` after the existing migrations. It is additive and idempotent; it creates no schedules and rewrites no job records or embeddings.
2. Start the web app with its existing distinct workspace/operator tokens and database configuration. Open `/operations` and unlock using the ingestion token.
3. Add a board you are authorized to collect, choosing an interval of **6–168 whole hours**. The interface always creates it **paused**. Up to **20 schedules**, including paused ones, can be stored.
4. Set `IMPORT_SCHEDULER_ENABLED=true` on the separate worker process and restart it. The accepted enabling values are `true` (case insensitive) and `1`; any other value is off. This setting does not start the worker. `DATABASE_URL` and embedding credentials are still required.
5. Click **Resume**. A resumed source is due immediately, but is admitted only when an opted-in worker polls and the shared budgets permit it. The dashboard reports a recent scheduler heartbeat separately from import-worker activity; neither is proof that a provider is reachable.

```sh
# Trusted shell with DATABASE_URL and OPENAI_API_KEY already configured:
export IMPORT_SCHEDULER_ENABLED=true
python -m rolecraft.worker
# Or, for an external timer/process runtime, one bounded tick:
python -m rolecraft.worker --once
```

On PowerShell, set `$env:IMPORT_SCHEDULER_ENABLED = 'true'`. For Compose use `docker compose -f compose.app.yml --profile live up --build`. Set identical import budget settings on web and worker so the displayed configured limits match execution. The web-process scheduler flag is diagnostic only; **the flag on the worker controls dispatch**. A Vercel web deployment does not host this persistent worker.

The no-credentials demo remains immutable: no schedules, live quotas, source activity, provider calls or heartbeats are fabricated. Both schedule mutations and manual runs fail closed in demo mode.

## Operator controls

**Edit interval** uses the revision captured when editing began. A competing session receives HTTP 409 instead of overwriting newer configuration. The draft remains visible on a conflict: refresh, cancel the old edit, and reopen the source to review the current configuration. Editing an enabled interval starts the new interval from the update time; resuming a paused schedule makes it due immediately.

**Pause** prevents future admissions by that schedule after the pause transaction commits. A dispatcher that obtained the row lock first may already have admitted a run; that run is preserved. **Remove** requires browser confirmation and deletes only the schedule. Neither operation deletes indexed jobs, revokes provider calls already in flight, nor cancels existing imports. Cancel admitted runs separately in import history.

**Run now** works even while a source is paused. It queues one run, or returns an already active run for that board without charging a second admission. It does not enable a paused schedule. A newly admitted manual run restarts the source's interval from that admission; reusing an active run does not postpone an existing deadline. A timeout is not proof of failure: refresh state before retrying.

The browser never writes operator tokens to local/session storage. Clearing access aborts client requests, erases schedule data and draft fields, and invalidates delayed responses. An abort does not undo a mutation already committed by the server.

## Transaction and recovery model

Each opted-in worker tick handles **at most one due schedule**, then processes at most one import work unit. The scheduler uses the PostgreSQL UTC clock and selects due enabled rows with `FOR UPDATE SKIP LOCKED`. Lock order is schedule row → source admission advisory lock → shared queue admission advisory lock. Import workers never acquire schedule row locks; preserve this order in future changes.

The existing queue admission method runs inside the schedule transaction. A successful admission, the linked run ID, and the next deadline commit together. A crash rolls them all back, including budget consumption. Multiple dispatchers cannot create two active runs for the same board. This is database admission idempotence, **not an exactly-once promise for upstream requests or provider billing**.

| Outcome | Persisted behavior |
|---|---|
| New run admitted | `queued`; next check is admission time + configured interval. |
| Board already active | `active`; reuse its ID and check again in five minutes; no new admission charged. |
| Queue already has 20 active runs | `queue_full`; check again in five minutes. |
| Daily admission budget exhausted | `daily_budget`; next check is the next UTC midnight. |
| No due sources | No run or provider request; a successful scheduler poll records its heartbeat. |
| Scheduler database error | Sanitized error log; already-admitted import work is still attempted. |

A long outage coalesces missed intervals into **one refresh**, rather than replaying every missed hour. This is an interval scheduler, not exact-clock cron: there is no specific local time, DST promise, or minute-level execution guarantee. Source order is oldest due deadline, then board token. Due times advance on budget/capacity deferral, preventing a hot retry loop.

The existing shared budgets remain **10 new queue runs per UTC day** and **200 job attempts per day by default**, with the latter configurable through `DAILY_IMPORT_JOB_LIMIT` (5–2,000). Failed/repeated indexing attempts still count. Twenty schedules do not imply capacity for twenty daily imports: choose intervals and limits intentionally. The legacy `/api/ingest` compatibility endpoint retains its separate request budget; it is not counted as durable-queue admission. The dashboard's “shared” limits refer to manual and recurring **durable queue** imports.

Snapshots are still bounded to 200 jobs and must complete while valid. Empty, oversized or expired snapshots fail without closing existing listings. Scheduling does not relax these protections. An unsuccessful scheduled run can be tried again at a subsequent interval; repeated invalid snapshots require operator review. Review the provider response and source scope rather than raising safety limits blindly.

## Freshness and history

Each saved source shows active roles and roles eligible under the **same freshness/expiry predicates used by retrieval**. The difference is the number of active roles excluded by age or explicit expiry. These counts do not verify employer claims or imply that every hard-filter combination has a match. “Last indexed record” is the latest source-record `last_seen`, not proof of a fully completed board refresh.

“Last retained successful import” comes from successful queue runs still in history. Pruning old run history may erase that timestamp and clears a deleted linked-run foreign key; it never removes schedules or indexed jobs. No last-success time is invented after pruning. The dashboard loads at most 20 sources and 40 recent import runs. Local-device times are used for display; quotas reset in UTC.

## API and direct-database CLI

All schedule routes require the separate ingestion token and live PostgreSQL. Bodies reject unknown fields and require real integer/boolean types. Board identifiers use the existing canonical 1–60 character ASCII token validator; URLs and arbitrary hosts are not accepted.

| Route | Contract |
|---|---|
| `GET /api/operations` | Includes `schedules`, scheduler heartbeat/configuration, budgets, and `can_schedule`. |
| `POST /api/source-schedules` | `{board, interval_hours: 24, enabled: false}` → 201. A duplicate board is 409. |
| `PUT /api/source-schedules/{board}` | `{interval_hours, enabled, expected_revision}` → updated revision; stale writes are 409. |
| `POST /api/source-schedules/{board}/run` | `{expected_revision}` → 202 for new run, 200 for reused active run. Requires embedding configuration. |
| `DELETE /api/source-schedules/{board}?expected_revision=N` | Deletes only that schedule; a stale revision is 409 and a missing schedule is 404. |

The CLI is for an operator with **direct database access**; it does not bypass the database's own authentication by using a web token. Never expose it as an unauthenticated web action. Secrets are environment variables, never command-line values.

```sh
python scripts/manage.py schedules add YOUR_BOARD --hours 24
python scripts/manage.py schedules list
# Read the current revision from list; these example writes assume it is 1.
python scripts/manage.py schedules update YOUR_BOARD --hours 24 --state enabled --revision 1
# Read the new revision before another update, run or remove:
python scripts/manage.py schedules run YOUR_BOARD --revision 2
python scripts/manage.py schedules update YOUR_BOARD --hours 24 --state paused --revision 2
python scripts/manage.py schedules remove YOUR_BOARD --revision 3
```

## Upgrade, rollback, and verification

Apply the migration before rolling out web and worker. If it is absent, the operations schema check fails rather than reporting that scheduling is ready. To stop recurring dispatch first pause sources or set the worker flag off and restart it. To roll back application code, leave the additive schedule table in place; 1.1 does not use it. Inspect/cancel already queued work separately. Never drop live data tables as an application rollback procedure.

CI tests actual PostgreSQL admission races, locked-row skipping, crash rollback, budget deferral, missed-interval coalescing, stale revision writes, retention and freshness. Private browser flows use the real HTTP application and database; the worker's upstream/embedding boundaries use explicit synthetic fixtures. One privacy race delays a real HTTP response. These tests do not prove paid credentials, real source availability, or a hosted deployment.

Before live use, perform a bounded authorized-source import and authenticated retrieval smoke test with real credentials. Check source evidence, confirmed hard-filter fields, job freshness, scheduler/worker heartbeats, budget settings, deployment commit, database backups and rollback access.

## Primary design references

- [PostgreSQL SELECT locking clauses](https://www.postgresql.org/docs/16/sql-select.html#SQL-FOR-UPDATE-SHARE)
- [PostgreSQL explicit locking](https://www.postgresql.org/docs/16/explicit-locking.html)
- [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html)
