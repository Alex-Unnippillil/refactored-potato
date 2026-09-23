# Security and data boundaries

## Secret handling

All provider keys and database credentials are server-side environment variables. `.env` and `.vercel` are ignored. The workspace token and the separate ingestion token must each contain at least 32 characters; use different randomly generated values. Browser tokens remain in memory, never in localStorage, cookies, exported shortlists or share URLs. Rotate tokens in Vercel and redeploy; clients must then re-enter the new token. This is shared-workspace authentication, not individual identity, multi-tenancy, or an audited role system.

Live searches fail closed when workspace access is not configured. Imports require an operator token and both database and embedding configuration. Provider/database failures never silently switch to demo data. Authenticated endpoints have no wildcard CORS permission. CSP blocks external scripts/styles and inline script execution; data attributes and text are escaped before rendering. Only HTTPS source links without user information are rendered.

## Data and execution boundaries

User values are parameters, never SQL fragments. Known filter columns are fixed in code. Actual request bodies are bounded at 256 KB and Pydantic rejects unknown fields. Provider requests have fixed API endpoints, timeouts, bounded batches, response validation and limited retry behavior. Search, brief and ingestion budgets are persisted in PostgreSQL, not a serverless process-local counter. These are cost guardrails, not a comprehensive DDoS defense; add Vercel firewall controls for a public service.

Greenhouse destinations are fixed and redirects are disabled. Firecrawl accepts only exact operator-approved hostnames, HTTPS port 443 and public DNS addresses. Those checks apply to the submitted URL; Firecrawl performs the downstream fetch. Upstream redirects, DNS changes and provider behavior still need review. Do not describe preliminary validation as a complete SSRF guarantee. Configure a managed crawl boundary and an explicit source allowlist; never add arbitrary user-supplied hosts.

Descriptions are untrusted content. They are stripped of HTML/scripts and never executed. Optional AI selects excerpts only, with no browsing, SQL, tools or deployment access. The returned IDs must match retrieved jobs and quotes must be exact substrings. This constrains output claims, but does not establish that the employer's statement or an extracted salary is true. Small local culture rules also do not reliably interpret negation; read the full quote.

## Operations

Use TLS and restricted database credentials. Use a migration role for DDL and a narrower runtime role. Restrict access to your database provider, enable backups and restore testing, and avoid exposing production credentials to untrusted preview branches. Raw errors and database URLs are not logged by application handlers; provider errors are generalized. Infrastructure access logs are controlled by the hosting provider and need their own retention review.

The included Docker database password is a clearly marked disposable local development fixture. Do not expose port 5432 to a public network. The integration test database is destructive and must be isolated from production.

Demo jobs are fictional. Live jobs and their source links remain in PostgreSQL; browser storage holds saved IDs and search presets, not access tokens. Shortlist exports deliberately include selected job details and source URLs; handle those files as your own saved data. Search URLs can include the user's query text; avoid entering personal documents or credentials.

No independent penetration test or security certification is claimed. Before operating as a public service, add identity-based authorization, tenant isolation, per-user abuse controls, a privacy/retention policy and incident response procedures appropriate to your deployment.

## Durable import controls (1.1)

Queue and cancellation routes require the separate ingestion token. The operations dashboard holds it only in page memory, clears the input immediately, removes private details on lock/navigation, and does not put it in localStorage, URLs or share links. The queue admits canonical board tokens only; callers cannot choose a worker request destination. Run metadata omits snapshots and lease tokens. Database-owned fencing protects cancelled/reclaimed jobs at commit. Empty/invalid/expired snapshots do not reconcile missing rows. A job-attempt budget bounds new paid indexing attempts, not exact provider charges. Keep provider-side spending controls enabled. The container runs as UID 10001 and supports a read-only root filesystem.


## Source schedules (1.2)

All schedule configuration and run-now endpoints require live PostgreSQL and the distinct ingestion token. The UI creates paused schedules and a separate worker flag opts into recurring dispatch. Fixed board-token validation prevents arbitrary target URLs; strict payload types, revision checks, admission caps and the existing daily job-attempt limits constrain writes. Pausing does not revoke a provider request already made. Client aborts do not undo committed mutations. No tokens enter local/session storage, screenshots, schedule rows or source bundles.
