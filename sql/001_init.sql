BEGIN;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS sources (
    key text PRIMARY KEY,
    label text NOT NULL,
    last_synced timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS jobs (
    id text PRIMARY KEY,
    title text NOT NULL,
    company text NOT NULL,
    country text NOT NULL,
    city text NOT NULL,
    work_mode text NOT NULL CHECK (work_mode IN ('Remote','Hybrid','On-site','Unknown')),
    level text NOT NULL CHECK (level IN ('Entry','Mid','Senior','Lead','Unknown')),
    salary_min integer CHECK (salary_min >= 0),
    salary_max integer CHECK (salary_max >= salary_min),
    currency text CHECK (currency IN ('CAD','USD','EUR','GBP')),
    salary_period text CHECK (salary_period = 'year'),
    description text NOT NULL,
    source_key text NOT NULL REFERENCES sources(key),
    first_seen timestamptz NOT NULL,
    last_seen timestamptz NOT NULL,
    expires_at timestamptz,
    active boolean NOT NULL DEFAULT true,
    payload jsonb NOT NULL,
    search_text tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title,'')), 'A') ||
        setweight(to_tsvector('english', coalesce(company,'')), 'B') ||
        setweight(to_tsvector('english', coalesce(description,'')), 'C')
    ) STORED,
    CHECK (salary_min IS NULL OR (currency IS NOT NULL AND salary_period = 'year'))
);
CREATE TABLE IF NOT EXISTS job_chunks (
    job_id text NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    ordinal integer NOT NULL,
    content text NOT NULL,
    embedding vector(1536) NOT NULL,
    embedding_model text NOT NULL CHECK (embedding_model = 'text-embedding-3-small'),
    PRIMARY KEY (job_id, ordinal)
);
CREATE INDEX IF NOT EXISTS jobs_metadata ON jobs (country, work_mode, level, salary_min) WHERE active;
CREATE INDEX IF NOT EXISTS jobs_search ON jobs USING gin(search_text);
CREATE INDEX IF NOT EXISTS jobs_freshness ON jobs (last_seen) WHERE active;
-- Included for measured ANN scaling. The default retrieval uses exact scoring
-- after metadata filtering, avoiding filtered-HNSW recall surprises.
CREATE INDEX IF NOT EXISTS chunks_hnsw ON job_chunks USING hnsw (embedding vector_cosine_ops);
CREATE TABLE IF NOT EXISTS usage_buckets (
    day date NOT NULL,
    kind text NOT NULL,
    used integer NOT NULL CHECK (used > 0),
    PRIMARY KEY (day, kind)
);
COMMIT;
