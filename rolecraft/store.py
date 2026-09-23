from __future__ import annotations

import json
import os
import sqlite3
import threading
from functools import lru_cache
from pathlib import Path

from .models import Filters, Job
from .text import chunk_text, concept_vector, cosine, tokens

ROOT = Path(__file__).resolve().parent.parent


def where_clause(filters: Filters, postgres: bool = False) -> tuple[str, list]:
    """Only known column names are interpolated. Every user value is bound."""
    placeholder = '%s' if postgres else '?'
    clauses = ['active = ' + ('true' if postgres else '1')]
    params: list = []
    if postgres:
        clauses += ["(expires_at IS NULL OR expires_at > now())", "last_seen > now() - (%s * interval '1 day')"]
        params.append(max(1, min(int(os.getenv('SOURCE_FRESH_DAYS', '14')), 90)))
    for column in ('country', 'work_mode', 'level'):
        value = getattr(filters, column)
        if value:
            clauses.append(f'{column} = {placeholder}')
            params.append(value)
    if filters.city:
        # Escape wildcard characters so a city is a literal substring, not SQL syntax.
        clauses.append(f"lower(city) LIKE {placeholder} ESCAPE '\\'")
        params.append('%' + filters.city.lower().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
    if filters.min_salary:
        clauses.extend([f'salary_min >= {placeholder}', f'currency = {placeholder}', "salary_period = 'year'"])
        params.extend([filters.min_salary, filters.currency])
    return ' AND '.join(clauses), params


class DemoStore:
    """Immutable demo corpus, queried by real SQLite/FTS5 and cosine vectors."""
    mode = 'demo'

    def __init__(self):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(':memory:', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('CREATE TABLE jobs (id TEXT PRIMARY KEY, country TEXT, city TEXT, work_mode TEXT, level TEXT, salary_min INTEGER, currency TEXT, salary_period TEXT, active INTEGER, payload TEXT)')
        self.db.execute('CREATE VIRTUAL TABLE job_fts USING fts5(id UNINDEXED, content)')
        self.jobs = [Job.model_validate(row).model_dump() for row in json.loads((ROOT / 'data/demo_jobs.json').read_text())]
        self.chunks = {}
        for job in self.jobs:
            self.db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)', (job['id'], job['country'], job['city'], job['work_mode'], job['level'], job['salary_min'], job['currency'], job['salary_period'], 1, json.dumps(job)))
            text = f"{job['title']} {job['company']} {' '.join(job['skills'])} {job['description']}"
            self.db.execute('INSERT INTO job_fts VALUES (?,?)', (job['id'], text))
            self.chunks[job['id']] = [concept_vector(f"{job['title']} {chunk}") for chunk in chunk_text(job['description'])]
        self.db.commit()

    def retrieve(self, query: str, filters: Filters, semantic: bool = True) -> dict:
        condition, args = where_clause(filters)
        with self.lock:
            eligible = [json.loads(row['payload']) for row in self.db.execute(f'SELECT payload FROM jobs WHERE {condition} ORDER BY id', args)]
            ids = {j['id'] for j in eligible}
            terms = tokens(query)[:40]
            lexical: list[tuple[str, float]] = []
            if terms:
                fts = ' OR '.join('"' + term + '"' for term in dict.fromkeys(terms))
                lexical = [(row['id'], -row['rank']) for row in self.db.execute('SELECT id, bm25(job_fts) AS rank FROM job_fts WHERE job_fts MATCH ? ORDER BY rank', (fts,)) if row['id'] in ids][:100]
        vector = concept_vector(query)
        ranked = sorted(((j['id'], max(cosine(vector, v) for v in self.chunks[j['id']])) for j in eligible), key=lambda x: (-x[1], x[0])) if query and semantic else []
        ranked = [(key, score) for key, score in ranked if score > 0.025][:100]
        return {'jobs': eligible, 'lexical': lexical, 'semantic': ranked, 'eligible_count': len(eligible)}

    def status(self) -> dict:
        return {'jobs': len(self.jobs), 'chunks': sum(map(len, self.chunks.values())), 'sources': 1}

    def find(self, ids: list[str]) -> list[dict]:
        return [j for j in self.jobs if j['id'] in ids]


class PostgresStore:
    mode = 'live'

    def connect(self):
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=8, row_factory=dict_row, options='-c statement_timeout=12000')

    def retrieve(self, query: str, filters: Filters, semantic: bool = True) -> dict:
        from .providers import EMBEDDING_MODEL, embed
        condition, args = where_clause(filters, True)
        query_vector = embed([query])[0] if query and semantic else None
        vector_text = '[' + ','.join(str(float(v)) for v in query_vector) + ']' if query_vector else None
        # Materialize the exact metadata-filtered relation before both retrieval
        # branches. Exact vector ranking here prioritizes strict-filter recall.
        # HNSW is supplied for future larger-scale, measured ANN deployments.
        prefix = f'WITH eligible AS MATERIALIZED (SELECT * FROM jobs WHERE {condition}) '
        with self.connect() as connection:
            total = connection.execute(f'SELECT count(*) AS n FROM jobs WHERE {condition}', args).fetchone()['n']
            if not query:
                rows = connection.execute(f'SELECT payload FROM jobs WHERE {condition} ORDER BY last_seen DESC, id LIMIT 100', args).fetchall()
                return {'jobs': [r['payload'] for r in rows], 'lexical': [], 'semantic': [], 'eligible_count': total}
            lexical = connection.execute(prefix + '''SELECT id, ts_rank_cd(search_text, websearch_to_tsquery('english', %s)) AS score
                FROM eligible WHERE search_text @@ websearch_to_tsquery('english', %s)
                ORDER BY score DESC, id LIMIT 100''', [*args, query, query]).fetchall()
            semantic_rows = []
            if vector_text:
                semantic_rows = connection.execute(prefix + '''SELECT e.id, max(1 - (c.embedding <=> %s::vector)) AS score
                    FROM eligible e JOIN job_chunks c ON c.job_id = e.id WHERE c.embedding_model = %s
                    GROUP BY e.id ORDER BY score DESC, e.id LIMIT 100''', [*args, vector_text, EMBEDDING_MODEL]).fetchall()
            semantic_rows = [r for r in semantic_rows if r['score'] > 0.1]
            ids = list(dict.fromkeys([r['id'] for r in lexical] + [r['id'] for r in semantic_rows]))
            jobs = [r['payload'] for r in connection.execute('SELECT payload FROM jobs WHERE id = ANY(%s)', (ids,)).fetchall()] if ids else []
        return {'jobs': jobs, 'lexical': [(r['id'], float(r['score'])) for r in lexical], 'semantic': [(r['id'], float(r['score'])) for r in semantic_rows], 'eligible_count': total}

    def status(self) -> dict:
        with self.connect() as connection:
            row = connection.execute('SELECT (SELECT count(*) FROM jobs WHERE active) AS jobs, (SELECT count(*) FROM job_chunks) AS chunks, (SELECT count(*) FROM sources) AS sources').fetchone()
        return dict(row)

    def find(self, ids: list[str]) -> list[dict]:
        with self.connect() as connection:
            return [r['payload'] for r in connection.execute('SELECT payload FROM jobs WHERE id = ANY(%s) AND active', (ids,)).fetchall()]

    def consume_budget(self, kind: str = 'search') -> bool:
        cap = max(1, min(int(os.getenv('DAILY_SEARCH_LIMIT', '250')), 10000))
        if kind == 'ingest':
            cap = min(cap, 50)
        with self.connect() as connection:
            row = connection.execute('''INSERT INTO usage_buckets (day, kind, used) VALUES (CURRENT_DATE, %s, 1)
                ON CONFLICT (day, kind) DO UPDATE SET used = usage_buckets.used + 1
                WHERE usage_buckets.used < %s RETURNING used''', (kind, cap)).fetchone()
        return row is not None

    def upsert_jobs(self, jobs: list[Job], source_key: str, source_label: str, complete: bool) -> int:
        from .providers import EMBEDDING_MODEL, embed
        # Network calls happen before transaction: failed embeddings never leave
        # partially indexed jobs. A bounded ingestion request accepts <= 10 jobs.
        pending, inputs = [], []
        for job in jobs:
            chunks = chunk_text(job.description)
            if len(chunks) > 48:
                raise ValueError('Description exceeds the indexing budget.')
            pending.append((job, chunks))
            inputs.extend(f'{job.title} — {job.company}\n{chunk}' for chunk in chunks)
        vectors = []
        for offset in range(0, len(inputs), 64):
            vectors.extend(embed(inputs[offset:offset + 64]))
        prepared, cursor = [], 0
        for job, chunks in pending:
            prepared.append((job, chunks, vectors[cursor:cursor + len(chunks)]))
            cursor += len(chunks)
        with self.connect() as connection:
            # Serialize syncs of the same source; a failed request rolls back all
            # writes, including deletion of old chunks and source bookkeeping.
            connection.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (source_key,))
            connection.execute('INSERT INTO sources (key, label, last_synced) VALUES (%s,%s,now()) ON CONFLICT (key) DO UPDATE SET label=EXCLUDED.label,last_synced=now()', (source_key, source_label))
            for job, chunks, vectors in prepared:
                payload = job.model_dump()
                existing = connection.execute('SELECT first_seen FROM jobs WHERE id=%s', (job.id,)).fetchone()
                if existing:
                    payload['first_seen'] = existing['first_seen'].isoformat()
                connection.execute('''INSERT INTO jobs (id,title,company,country,city,work_mode,level,salary_min,salary_max,currency,salary_period,description,source_key,first_seen,last_seen,expires_at,active,payload)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,%s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title,company=EXCLUDED.company,country=EXCLUDED.country,city=EXCLUDED.city,work_mode=EXCLUDED.work_mode,level=EXCLUDED.level,salary_min=EXCLUDED.salary_min,salary_max=EXCLUDED.salary_max,currency=EXCLUDED.currency,salary_period=EXCLUDED.salary_period,description=EXCLUDED.description,last_seen=EXCLUDED.last_seen,expires_at=EXCLUDED.expires_at,active=true,payload=EXCLUDED.payload''',
                    (job.id,job.title,job.company,job.country,job.city,job.work_mode,job.level,job.salary_min,job.salary_max,job.currency,job.salary_period,job.description,source_key,payload['first_seen'],job.last_seen,job.expires_at,json.dumps(payload)))
                connection.execute('DELETE FROM job_chunks WHERE job_id=%s', (job.id,))
                for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
                    connection.execute('INSERT INTO job_chunks (job_id,ordinal,content,embedding,embedding_model) VALUES (%s,%s,%s,%s::vector,%s)', (job.id,index,chunk,'['+','.join(map(str,vector))+']',EMBEDDING_MODEL))
            if complete:
                connection.execute('UPDATE jobs SET active=false WHERE source_key=%s AND NOT (id = ANY(%s))', (source_key,[j.id for j in jobs]))
        return len(jobs)


@lru_cache(maxsize=1)
def demo_store() -> DemoStore:
    return DemoStore()


def get_store() -> DemoStore | PostgresStore:
    # No silent fallback to fictional data on a live database failure.
    return PostgresStore() if os.getenv('DATABASE_URL') else demo_store()
