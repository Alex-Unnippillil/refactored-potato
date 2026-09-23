"""Real PostgreSQL + pgvector contract tests; never call a paid model API.

Set TEST_DATABASE_URL to a DISPOSABLE database; this module deletes test rows.
CI provisions a dedicated pgvector service. No production URL is ever inherited.
"""
import os
from pathlib import Path

import pytest

from rolecraft.models import Filters, Job, SearchRequest, utcnow
from rolecraft.store import PostgresStore, demo_store
from rolecraft.search import search
from rolecraft.text import concept_vector

pytestmark = pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'), reason='A disposable PostgreSQL/pgvector database is required')


def embedding(texts):
    return [concept_vector(text) + [0.0] * (1536 - 256) for text in texts]


@pytest.fixture
def pg(monkeypatch):
    psycopg = pytest.importorskip('psycopg')
    monkeypatch.setenv('DATABASE_URL', os.environ['TEST_DATABASE_URL'])
    monkeypatch.delenv('COHERE_API_KEY', raising=False)
    monkeypatch.setattr('rolecraft.providers.embed', embedding)
    with psycopg.connect(os.environ['TEST_DATABASE_URL'], autocommit=True) as connection:
        connection.execute((Path(__file__).resolve().parents[1] / 'sql/001_init.sql').read_text())
        connection.execute('TRUNCATE jobs, sources, job_chunks, usage_buckets CASCADE')
    store = PostgresStore()
    rows = []
    for data in demo_store().jobs:
        row = dict(data)
        row.update(is_demo=False, source_key='test:fixture', source='Integration fixture', source_url='https://example.com/jobs/' + row['id'], last_seen=utcnow())
        rows.append(Job.model_validate(row))
    store.upsert_jobs(rows, 'test:fixture', 'Integration fixture', complete=True)
    return store, rows


def test_schema_storage_and_idempotent_upsert(pg):
    store, rows = pg
    before = store.status()
    assert before['jobs'] == 24 and before['chunks'] >= 24
    store.upsert_jobs(rows, 'test:fixture', 'Integration fixture', complete=True)
    assert store.status() == before


def test_both_branches_enforce_hard_filters(pg):
    store, _ = pg
    # The deterministic test embedder has no broad learned meaning for the lone
    # token 'engineer'. Use an in-ontology term to exercise vector retrieval above
    # the unchanged production similarity floor, alongside lexical retrieval.
    request = SearchRequest(query='python engineer', filters=Filters(country='Canada', work_mode='Remote', min_salary=140000), page_size=24)
    raw = store.retrieve(request.query, request.filters)
    eligible_ids = {'demo-01', 'demo-04', 'demo-08'}
    assert raw['lexical'] and raw['semantic']
    assert {identifier for identifier, _ in raw['lexical']} <= eligible_ids
    assert {identifier for identifier, _ in raw['semantic']} <= eligible_ids
    result = search(request, store)
    assert result['jobs'] and result['trace']['semantic_candidates'] > 0
    assert result['trace']['lexical_candidates'] > 0
    assert all(j['country'] == 'Canada' and j['work_mode'] == 'Remote' and j['salary_min'] >= 140000 and j['currency'] == 'CAD' for j in result['jobs'])


def test_sql_injection_and_currency_contract(pg):
    store, _ = pg
    assert search(SearchRequest(filters=Filters(city="Toronto' OR 1=1 --")), store)['total'] == 0
    result = search(SearchRequest(filters=Filters(min_salary=1, currency='USD'), page_size=24), store)
    assert result['jobs'] and all(j['currency'] == 'USD' for j in result['jobs'])


def test_closed_expired_and_stale_records_are_excluded(pg):
    store, rows = pg
    with store.connect() as conn:
        conn.execute('UPDATE jobs SET active=false WHERE id=%s', (rows[0].id,))
        conn.execute("UPDATE jobs SET last_seen=now()-interval '31 days' WHERE id=%s", (rows[1].id,))
        conn.execute("UPDATE jobs SET expires_at=now()-interval '1 day' WHERE id=%s", (rows[2].id,))
    result = search(SearchRequest(page_size=24), store)
    assert result['total'] == 21
    assert not {rows[i].id for i in range(3)} & {j['id'] for j in result['jobs']}


def test_complete_snapshot_closes_missing_jobs(pg):
    store, rows = pg
    store.upsert_jobs(rows[:2], 'test:fixture', 'Integration fixture', complete=True)
    assert store.status()['jobs'] == 2
    assert len(store.find([r.id for r in rows])) == 2


def test_partial_snapshot_does_not_close_unseen_jobs(pg):
    store, rows = pg
    store.upsert_jobs(rows[:2], 'test:fixture', 'Integration fixture', complete=False)
    assert store.status()['jobs'] == 24


def test_embedding_failure_cannot_partially_write(pg, monkeypatch):
    store, rows = pg
    before = store.status()
    def failure(_):
        raise RuntimeError('simulated provider outage')
    monkeypatch.setattr('rolecraft.providers.embed', failure)
    with pytest.raises(RuntimeError):
        store.upsert_jobs(rows[:2], 'test:fixture', 'Integration fixture', complete=True)
    assert store.status() == before


def test_request_budget_is_persistent_and_bounded(pg, monkeypatch):
    store, _ = pg
    monkeypatch.setenv('DAILY_SEARCH_LIMIT', '2')
    assert store.consume_budget('search') is True
    assert store.consume_budget('search') is True
    assert store.consume_budget('search') is False
    assert store.consume_budget('brief') is True
    with store.connect() as conn:
        assert conn.execute("SELECT used FROM usage_buckets WHERE kind='search'").fetchone()['used'] == 2
