BEGIN;
-- No recurring import is enabled by this additive migration.
CREATE TABLE IF NOT EXISTS source_schedules (
    board text PRIMARY KEY CHECK (board ~ '^[a-z0-9_-]{1,60}$'),
    interval_hours integer NOT NULL DEFAULT 24 CHECK (interval_hours BETWEEN 6 AND 168),
    enabled boolean NOT NULL DEFAULT false,
    next_run_at timestamptz NOT NULL DEFAULT now(),
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    last_dispatch_at timestamptz,
    last_queued_at timestamptz,
    last_run_id text REFERENCES import_runs(id) ON DELETE SET NULL,
    dispatch_status text NOT NULL DEFAULT 'never'
        CHECK (dispatch_status IN ('never','queued','active','daily_budget','queue_full'))
);
CREATE INDEX IF NOT EXISTS due_source_schedules ON source_schedules(next_run_at, board) WHERE enabled;
CREATE INDEX IF NOT EXISTS import_runs_board_history ON import_runs(board, finished_at DESC)
    WHERE state = 'succeeded';
COMMIT;
