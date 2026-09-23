# Rolecraft

**Find work that fits the way you want to work.**

![CI](https://github.com/Alex-Unnippillil/refactored-potato/actions/workflows/ci.yml/badge.svg)

**Release 1.1 — durable imports, operational readiness, and reproducible delivery.**

[Run locally](#run-the-demo) · [Live workspace](#live-workspace) · [Durable imports](docs/RELIABLE_IMPORTS.md) · [Operations](docs/OPERATIONS.md) · [Security](docs/SECURITY.md)

Rolecraft is a complete job-search workspace built around a hybrid retrieval pipeline: structured SQL constraints, full-text search, description vectors, reciprocal-rank fusion, re-ranking, and source-backed evidence briefs. A responsive interface makes the pipeline useful rather than hiding it behind a chat box.

> The default workspace contains **24 fictional companies and jobs**. It works without API keys, does not scrape automatically, and does not call a paid AI provider. Its concept vectors are explicitly **not a pretrained neural embedding model**. Live mode requires your database and server-side credentials; it never falls back to fictional results when a backend fails.

## The working application

The screenshots below are captured from the **running HTTP demo**, not design mockups. Demo data is fictional and the import worker is correctly shown as off. CI regenerates screenshots as downloadable artifacts; `python scripts/capture_screenshots.py` refreshes the committed images during development.

### Search workspace — desktop
![Rolecraft desktop: explicit filters, natural-language query, saved roles and evidence-backed results](docs/assets/workspace-desktop.png)

### Operations — desktop
![Rolecraft operations: actual demo counts, readiness checks, disabled live import control and honest empty run history](docs/assets/operations-desktop.png)

<details>
<summary>Mobile screenshots — 390-pixel viewport, captured at 2× resolution</summary>

<img src="docs/assets/workspace-mobile.png" width="390" alt="Rolecraft job search on a narrow mobile viewport">
<img src="docs/assets/operations-mobile.png" width="390" alt="Rolecraft operational readiness on a narrow mobile viewport">

</details>

## System architecture

![Rolecraft architecture: structured and semantic retrieval, durable source snapshots, separate worker, fenced atomic indexing, and an isolated fictional demo](docs/assets/architecture.svg)

The web process handles bounded requests. PostgreSQL owns the durable import state. The worker runs separately from Vercel web requests. **No process-local background task is presented as a durable job.**

## What is included

- Natural-language relevance search alongside explicit country, city, work style, experience, annual base salary and currency filters. SQL applies the filters before **both** retrieval branches.
- Six optional preferences: asynchronous work, sustainable pace, ownership, mentorship, meaningful work and learning. Keywords-only, meaning-only and hybrid views make retrieval behavior inspectable.
- Exact evidence excerpts, unconfirmed preferences, raw retrieval diagnostics and an evidence brief. No invented match percentages or promises about company culture.
- Saved roles and searches, up-to-three-role comparison, shortlist export, shareable search URLs, keyboard shortcuts, touch-friendly navigation, and mobile filters.
- Live PostgreSQL/pgvector storage, Greenhouse board imports, an allowlisted Firecrawl adapter, and validated JSON imports. Optional Cohere re-ranking and OpenAI excerpt selection.
- A durable Greenhouse import queue: one persisted snapshot, restartable five-job units, fenced leases, cancellation, bounded retries, job-attempt budgets and closure only on complete success.
- An operator dashboard at `/operations` with actual readiness, run history, refresh controls and a recent-worker heartbeat. The demo never invents worker activity.
- Additive migrations, operator and worker CLIs, real PostgreSQL concurrency tests, three-browser verification, non-root container smoke tests, and reproducible screenshots.

## Run the demo

**Container path:** with Docker installed, run `docker compose -f compose.app.yml up --build` and open **http://127.0.0.1:8000**. Leave `DATABASE_URL` unset to stay in demo mode. The worker starts only with the explicit `live` profile.

**Python path:** use Python 3.12 or newer. No frontend build step or Node dependencies are required.

```sh
python -m venv .venv
# macOS/Linux:
. .venv/bin/activate
# Windows PowerShell instead:
# .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload
```

Open **http://127.0.0.1:8000**. Keep `DATABASE_URL` unset for the demo. The demo SQL/FTS index is immutable and initialized in memory; saved role IDs and search presets remain in browser storage.

Try: **“Backend engineering with Python or Go, a calm team and protected focus time”**, select Canada + Remote, then asynchronous work and sustainable pace. A natural-language salary or location mention is a relevance term only: use the explicit controls for enforceable constraints. Salaries are not converted between currencies; the minimum compares against the advertised annual base **lower bound**. Undisclosed pay does not pass a minimum-pay filter.

## Live workspace

### 1. Provision PostgreSQL with pgvector

Use a database/provider that supports the `vector` extension, with TLS and a suitable pooled connection endpoint for serverless workloads. Keep runtime privileges restricted; run extension/schema setup with a separate migration-capable identity.

For a disposable local database:

```sh
docker compose up -d
# The compose credentials below are local development fixtures, not production secrets.
export DATABASE_URL='postgresql://rolecraft:local-development-only@localhost:5432/rolecraft'
python scripts/manage.py migrate
```

On PowerShell, use `$env:DATABASE_URL = '...'` instead of `export`. Environment variables are read from the running process. **Copying `.env.example` to `.env` alone does not load it.** Use your shell, a trusted environment loader, or the Vercel environment-variable UI. Never commit `.env`.

### 2. Configure secrets

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string; setting it selects live mode. |
| `APP_ACCESS_TOKEN` | Strong, randomly generated 32+ character workspace token. Required in live mode. |
| `INGEST_TOKEN` | A different, strong 32+ character operator token for imports. |
| `OPENAI_API_KEY` | Embedding credentials. The schema pins `text-embedding-3-small` at 1,536 dimensions. |
| `COHERE_API_KEY` | Optional cross-encoder re-ranking; the default model is `rerank-v3.5`. |
| `FIRECRAWL_API_KEY` | Optional authorized single-page extraction. |
| `SCRAPE_ALLOWED_HOSTS` | Exact comma-separated career-page hosts permitted for Firecrawl; empty denies all. |
| `OPENAI_CHAT_MODEL` | Optional model supporting strict JSON-schema responses, for selecting source excerpts. No default generative model is enabled. |
| `DAILY_SEARCH_LIMIT` | Daily per-workspace limit for searches **and separately** briefs; default 250 each. Imports have a separate limit capped at 50 requests/day. |
| `DAILY_IMPORT_JOB_LIMIT` | Durable worker job-attempt budget per UTC day; default 200, bounded 5–2,000. Failed/repeated attempts count too. |
| `SOURCE_FRESH_DAYS` | Exclude live records not refreshed within this many days; default 14, bounded 1–90. |

Generate different access tokens locally using a trusted password manager or `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Store them in your deployment secret manager, not this repository or a chat message. The web client keeps access tokens only in page memory. This is a **single private workspace**, not a multi-tenant account/SSO system.

### 3. Start the separate durable worker

```sh
python -m rolecraft.worker
# One bounded unit instead of a persistent process:
python -m rolecraft.worker --once
```

Open **`/operations`**, unlock with the ingestion token, and queue a Greenhouse board token. Imports persist across browser refreshes and worker restarts. Run `python scripts/manage.py migrate` before the web/worker upgrade; it now applies both numbered migrations. [State machine, limits, deployment and recovery](docs/RELIABLE_IMPORTS.md).

### 4. Direct import compatibility

In **Data sources**, enter a Greenhouse board token or an allowlisted Firecrawl job-page URL and the separate ingestion token. The UI imports a bounded batch of at most five Greenhouse jobs. The CLI can visit all batches:

```sh
# INGEST_TOKEN is read from the environment, never a command-line argument.
python scripts/manage.py sync YOUR_BOARD --all --base-url https://YOUR-WORKSPACE.vercel.app
python scripts/manage.py status
```

The Greenhouse adapter uses its official public Job Board API, not an HTML crawler. Importing a large board is bounded and restartable; retry with `--offset N`. Each batch obtains a fresh upstream snapshot, so a rapidly changing board can shift between batches. Repeated periodic synchronization and freshness expiry mitigate this; the new `/operations` queue avoids shifting offsets by preserving one validated snapshot (up to 200 jobs). Only a complete small-board snapshot closes missing rows immediately. Partial batches never close unseen jobs.

Unknown compensation and eligibility remain unknown. Greenhouse metadata is conservative: countries and work styles are populated only when explicitly named in the source location; missing salary is not guessed. Verify imported fields before relying on filters. Firecrawl output is schema-validated but remains model-extracted source data, not independently verified fact.

Validated JSON imports are supported at `POST /api/ingest` with `provider: "json"`, 1–10 `Job` records and HTTPS source links. IDs are normalized into an import-specific namespace. See `rolecraft/models.py` and `tests/test_api.py` for contracts.

## How retrieval works

```text
Authorized source → normalize + retain provenance → 1,100-character chunks / 160 overlap
                            ↓
          PostgreSQL jobs + full-text index + pgvector chunks
                            ↓
Request → parameterized SQL metadata filters → eligible jobs
                            ↙                   ↘
                  full-text retrieval       cosine retrieval
                            ↘                   ↙
                    job-level deduplication + weighted RRF (k=60)
                                      ↓
                evidence-aware re-ranking / optional Cohere top 40
                                      ↓
              ranked roles + exact excerpts + verified evidence brief
```

Demo mode uses real SQLite SQL and FTS5 plus deterministic, hand-built 256-dimensional concept vectors. It demonstrates data flow without downloading model weights. It has limited vocabulary, hash collisions, and no learned multilingual understanding. It must not be benchmarked as a neural system.

Live mode uses weighted PostgreSQL full-text retrieval and OpenAI 1,536-dimensional embeddings. The default vector query scores the **exact metadata-filtered relation** to avoid approximate-index filtering surprises. An HNSW index is supplied in the schema, but the default query deliberately does not claim ANN acceleration. Each branch is capped at 100 candidates; browse is also capped at 100. The UI exposes the candidate cap, eligible count, ranking method and timings. For larger corpora, measure recall/latency before changing to filtered ANN, iterative scans, partitioning or an external vector service.

The first three results can become an evidence brief. Without a chat model, it is extractive. With one configured, the model may **select** quotes, not freely invent job facts. Every selected ID and contiguous excerpt is checked against an indexed description; invalid output falls back to verified excerpts. Source text never receives SQL or tool permissions.

## Deploy on Vercel

Import **Alex-Unnippillil/refactored-potato** as a new project in your Vercel team. Choose the **FastAPI** framework preset, repository root, and `main` as production branch. No custom build command or frontend output directory is needed. `app.py` exports the FastAPI instance, `requirements.txt` pins runtime dependencies, and `public/` holds static assets.

Deploy without secrets to publish the clearly labelled demo. To activate live mode, first provision and migrate PostgreSQL, then configure the variables above on the appropriate Vercel environment and redeploy. Keep production credentials out of preview deployments unless explicitly authorized.

For a connected local checkout with an authenticated Vercel CLI:

```sh
vercel link
vercel deploy
# Verify the preview, then:
vercel deploy --prod
```

Vercel hosts the web app, **not the persistent import worker**. Run the worker in a container/VM or other approved process runtime connected to the same database. No paid resource is provisioned automatically. A deployment URL and real-provider smoke test must be verified separately; repository CI is not a claim that a hosted production instance exists.

Do not treat a successful `/api/health` response as database/provider readiness. `/api/readiness` checks the configured store and corpus without calling paid providers. That endpoint is liveness only. In live mode, run an authenticated search, inspect evidence and source freshness, and verify the expected commit in Vercel's deployment details. See [operations](docs/OPERATIONS.md) and [security](docs/SECURITY.md).

## Tests and evaluation

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
python scripts/evaluate.py
node --check public/app.js
```

PostgreSQL tests intentionally skip without `TEST_DATABASE_URL`. Set that variable to a **disposable** database: the fixture truncates its tables. It never uses a production `DATABASE_URL` implicitly. Provider calls are mocked in integration tests; API keys are not needed.

For actual browser/HTTP tests, start the app at port 8000, then:

```sh
python -m playwright install --with-deps chromium firefox webkit
RUN_UI_TESTS=1 TEST_BROWSER=chromium python -m pytest tests/test_ui.py -q
RUN_UI_TESTS=1 TEST_BROWSER=firefox python -m pytest tests/test_ui.py -q
RUN_UI_TESTS=1 TEST_BROWSER=webkit python -m pytest tests/test_ui.py -q
```

On Windows, set the two variables with `$env:RUN_UI_TESTS='1'` and `$env:TEST_BROWSER='chromium'` before invoking pytest. CI provisions a real pgvector database and uses normal browser HTTP navigation without mocks. An optional `UI_TEST_MODE=bridge` harness supports restricted offline sandboxes; its network/history/storage substitutions **do not constitute deployment, CSP, browser persistence or network verification**.

The evaluator reports MRR and nDCG@10 over eight authored queries against the fictional corpus. These are reproducible regression diagnostics, **not a held-out benchmark or evidence of real-world hiring quality**.

## Project map

```text
app.py                    HTTP routes, private access, budgets and headers
rolecraft/models.py       Validated input and job contracts
rolecraft/store.py        SQLite demo and PostgreSQL retrieval/atomic indexing
rolecraft/text.py         Chunking, demo vectors, exact evidence spans
rolecraft/search.py       Fusion, re-ranking, pagination and traces
rolecraft/providers.py    Bounded OpenAI/Cohere provider calls
rolecraft/ingest.py        Greenhouse and allowlisted Firecrawl adapters
rolecraft/brief.py         Extractive / AI-selected source-checked briefs
rolecraft/import_queue.py  PostgreSQL admission, leases, cursor checkpoints, cancellation
rolecraft/worker.py        Separate bounded snapshot/indexing worker
rolecraft/operations.py    Safe readiness, queue API and operator pages
public/                   Responsive dependency-free interface
sql/001_init.sql          PostgreSQL/pgvector schema and indexes
sql/002_imports.sql       Additive durable run and heartbeat schema
Dockerfile               Non-root, read-only-compatible web/worker image
compose.app.yml          Local demo plus explicit live worker profile
scripts/manage.py         Migration, source sync and inspection CLI
scripts/evaluate.py       Retrieval regression evaluation
scripts/capture_screenshots.py  Reproducible real-HTTP demo screenshots
tests/                   API, security, retrieval, database and browser tests
```

## Limits and next scaling steps

This release does not include recurring crawling, application submission, resume ingestion, employer verification, account synchronization, per-user permissions, a managed worker hosting service, or a pretrained offline embedding model. No provider account or paid database is provisioned by the source code. Source freshness is bounded, not real-time. Authored culture signals are lexical evidence cues and do not robustly understand negation, sarcasm or workplace truth; confirm them with an employer.

For a public multi-user service, replace the shared token with an audited identity provider and tenant-scoped authorization, add per-user quotas/rate controls, operate the included durable import queue and add periodic source scheduling, run a real labelled retrieval evaluation, and add monitoring/backups. Keep operator imports private. Review source terms, robots policies and licensing before collection; the app does not bypass access controls.

### Technical references

- [pgvector: hybrid search, indexes and filtering](https://github.com/pgvector/pgvector)
- [Greenhouse Job Board API](https://developers.greenhouse.io/job-board.html)
- [Firecrawl scrape API](https://docs.firecrawl.dev/api-reference/endpoint/scrape)
- [OpenAI embeddings](https://developers.openai.com/api/docs/guides/embeddings)
- [Cohere re-ranking](https://docs.cohere.com/reference/rerank)
- [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi)


## Release verification

The CI workflow runs every backend test against a disposable pgvector database, checks JavaScript syntax, tests normal HTTP navigation in Chromium/Firefox/WebKit, captures four screenshots, and builds/runs the non-root Docker image. Live providers are mocked at their boundaries; these tests do not prove real provider credentials or paid quotas are available. See [the durable-import runbook](docs/RELIABLE_IMPORTS.md) before enabling live collection.
