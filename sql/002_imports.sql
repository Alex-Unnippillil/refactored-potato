BEGIN;
-- Additive migration: existing jobs and embeddings are not rewritten.
CREATE TABLE IF NOT EXISTS import_runs (
    id text PRIMARY KEY,
    board text NOT NULL,
    state text NOT NULL DEFAULT 'queued'
        CHECK (state IN ('queued','running','retry','succeeded','failed','cancelled')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    available_at timestamptz NOT NULL DEFAULT now(),
    lease_until timestamptz,
    lease_token text,
    claims integer NOT NULL DEFAULT 0 CHECK (claims >= 0),
    failures integer NOT NULL DEFAULT 0 CHECK (failures BETWEEN 0 AND 3),
    processed integer NOT NULL DEFAULT 0 CHECK (processed >= 0),
    total integer NOT NULL DEFAULT 0 CHECK (total BETWEEN 0 AND 200),
    snapshot jsonb,
    snapshot_at timestamptz,
    error_code text,
    finished_at timestamptz,
    CHECK (processed <= total),
    CHECK (snapshot IS NULL OR jsonb_typeof(snapshot) = 'array'),
    CHECK (state <> 'running' OR (lease_until IS NOT NULL AND lease_token IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_import_per_board ON import_runs(board)
    WHERE state IN ('queued','running','retry');
CREATE INDEX IF NOT EXISTS import_dispatch ON import_runs(available_at, created_at)
    WHERE state IN ('queued','running','retry');
CREATE TABLE IF NOT EXISTS worker_heartbeat (
    name text PRIMARY KEY,
    last_seen timestamptz NOT NULL DEFAULT now()
);
COMMIT;
