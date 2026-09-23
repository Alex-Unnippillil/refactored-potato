"""Disposable PostgreSQL tests for leases, durable snapshots and batch atomicity."""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rolecraft.import_queue import ImportQueue, LeaseLost, QueueBudget, QueueConflict, board_token, public_run
from rolecraft.models import Job, utcnow
from rolecraft.providers import ProviderError
from rolecraft.store import PostgresStore, demo_store
from rolecraft.worker import tick


def jobs(n=7, board='acme'):
    template = dict(demo_store().jobs[0])
    template.update(company=board, source_key='greenhouse:' + board, source='Greenhouse', is_demo=False,
                    first_seen=utcnow(), last_seen=utcnow())
    return [Job.model_validate({**template, 'id':f'gh-{board}-{i}', 'source_url':f'https://example.com/jobs/{board}/{i}'}) for i in range(n)]


@pytest.fixture
def queue(monkeypatch):
    if not os.getenv('TEST_DATABASE_URL'):
        pytest.skip('Needs a disposable PostgreSQL/pgvector database')
    import psycopg
    monkeypatch.setenv('DATABASE_URL', os.environ['TEST_DATABASE_URL'])
    monkeypatch.setenv('APP_ACCESS_TOKEN', 'workspace-test-' + 'a'*32)
    monkeypatch.setenv('INGEST_TOKEN', 'operator-test-' + 'b'*32)
    monkeypatch.setenv('OPENAI_API_KEY', 'test-only-not-real')
    monkeypatch.setenv('DAILY_IMPORT_JOB_LIMIT', '200')
    monkeypatch.delenv('OPENAI_EMBEDDING_MODEL', raising=False)
    monkeypatch.setattr('rolecraft.providers.embed', lambda texts: [[1.0]+[0.0]*1535 for _ in texts])
    root = Path(__file__).resolve().parents[1]
    with psycopg.connect(os.environ['TEST_DATABASE_URL'], autocommit=True) as conn:
        for migration in sorted((root/'sql').glob('*.sql')):
            conn.execute(migration.read_text())
        conn.execute('TRUNCATE import_runs,worker_heartbeat,jobs,job_chunks,sources,usage_buckets CASCADE')
    return ImportQueue()


def due(queue):
    with queue.store.connect() as conn:
        conn.execute("UPDATE import_runs SET available_at=now() WHERE state='retry'")


@pytest.mark.parametrize('value',['https://example.com','../acme','x; DROP TABLE jobs','équipe','a'*61,' acme','acme\n',''])
def test_board_validation(value):
    with pytest.raises(ValueError):
        board_token(value)


def test_board_canonicalization():
    assert board_token('Acme_Jobs-1') == 'acme_jobs-1'


def test_enqueue_is_idempotent_and_private(queue):
    first, created = queue.enqueue('ACME')
    again, new = queue.enqueue('acme')
    assert created and not new and first['id'] == again['id']
    claimed = queue.claim()
    assert {'snapshot','lease_token','lease_until'}.isdisjoint(public_run(claimed))
    with queue.store.connect() as conn:
        assert conn.execute("SELECT used FROM usage_buckets WHERE kind='queue_requests'").fetchone()['used'] == 1


def test_parallel_admission_has_one_run(queue):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: ImportQueue().enqueue('acme'), range(4)))
    assert sum(created for _, created in results) == 1
    assert len({row['id'] for row, _ in results}) == 1


def test_daily_admission_budget(queue):
    for i in range(10):
        queue.enqueue(f'board-{i}')
    with pytest.raises(QueueBudget):
        queue.enqueue('extra')
    assert len(queue.recent()) == 10


def test_claim_skips_locked_run(queue):
    first, _ = queue.enqueue('first')
    second, _ = queue.enqueue('second')
    with queue.store.connect() as held:
        held.execute('SELECT id FROM import_runs WHERE id=%s FOR UPDATE', (first['id'],))
        claimed = queue.claim()
        assert claimed['id'] == second['id']


def test_snapshot_resume_fetches_only_once(queue, monkeypatch):
    calls = []
    def fetch(*_):
        calls.append(1)
        return jobs(), 7, True
    monkeypatch.setattr('rolecraft.worker.fetch_board', fetch)
    queue.enqueue('acme')
    assert tick(queue)
    assert queue.recent()[0]['processed'] == 5
    assert queue.recent()[0]['state'] == 'queued'
    assert tick(ImportQueue())  # another process can resume the persisted cursor
    result = queue.recent()[0]
    assert result['state'] == 'succeeded' and result['processed'] == 7
    assert len(calls) == 1 and queue.store.status()['jobs'] == 7
    with queue.store.connect() as conn:
        assert conn.execute('SELECT snapshot FROM import_runs').fetchone()['snapshot'] is None
    assert tick(queue) is False


def test_closure_only_after_full_snapshot_success(queue, monkeypatch):
    old = jobs(9)
    queue.store.upsert_jobs(old, 'greenhouse:acme', 'Acme', False)
    queue.store.upsert_jobs(jobs(1,'other'), 'greenhouse:other', 'Other', False)
    monkeypatch.setattr('rolecraft.worker.fetch_board', lambda *_: (jobs(), 7, True))
    queue.enqueue('acme')
    tick(queue)
    assert queue.store.status()['jobs'] == 10
    tick(queue)
    assert queue.store.status()['jobs'] == 8
    assert queue.store.find(['gh-acme-8']) == []
    assert queue.store.find(['gh-other-0'])


def test_invalid_snapshot_does_not_close_existing_jobs(queue, monkeypatch):
    queue.store.upsert_jobs(jobs(1), 'greenhouse:acme', 'Acme', False)
    monkeypatch.setattr('rolecraft.worker.fetch_board', lambda *_: ([], 0, True))
    queue.enqueue('acme'); tick(queue)
    assert queue.recent()[0]['state'] == 'failed'
    assert queue.store.status()['jobs'] == 1


@pytest.mark.parametrize('kind',['oversize','duplicates','wrong_source'])
def test_bad_snapshots_are_rejected(queue, kind):
    queue.enqueue('acme'); run=queue.claim()
    data = jobs(201) if kind == 'oversize' else jobs(1)*2 if kind == 'duplicates' else jobs(1,'other')
    with pytest.raises(ValueError):
        queue.set_snapshot(run, data)
    assert queue.store.status()['jobs'] == 0


def test_retry_preserves_snapshot_and_cursor(queue, monkeypatch):
    calls=[]
    monkeypatch.setattr('rolecraft.worker.fetch_board', lambda *_: (calls.append(1) or jobs(), 7, True))
    good = lambda texts: [[1.0]+[0.0]*1535 for _ in texts]
    queue.enqueue('acme'); tick(queue)
    def fail(_):
        raise ProviderError('Upstream failed without leaking its body.')
    monkeypatch.setattr('rolecraft.providers.embed', fail)
    tick(queue)
    assert queue.recent()[0]['state']=='retry' and queue.recent()[0]['processed']==5
    assert queue.store.status()['jobs']==5
    due(queue); monkeypatch.setattr('rolecraft.providers.embed', good); tick(queue)
    assert queue.recent()[0]['state']=='succeeded' and len(calls)==1


def test_cancellation_fences_inflight_worker(queue):
    queue.enqueue('acme'); run=queue.claim(); queue.set_snapshot(run,jobs(1))
    queue.cancel(run['id'])
    with pytest.raises(LeaseLost):
        queue.store.upsert_jobs(jobs(1),'greenhouse:acme','Acme',False,transaction_hook=lambda c: queue.checkpoint(c,run,1))
    assert queue.store.status()['jobs']==0
    assert queue.recent()[0]['state']=='cancelled'


def test_expired_worker_cannot_commit_after_reclaim(queue):
    queue.enqueue('acme'); old=queue.claim(); queue.set_snapshot(old,jobs(1))
    with queue.store.connect() as conn:
        conn.execute("UPDATE import_runs SET lease_until=now()-interval '1 second'")
    new=queue.claim()
    assert new['lease_token'] != old['lease_token'] and new['failures']==1
    with pytest.raises(LeaseLost):
        with queue.store.connect() as conn:
            queue.checkpoint(conn,old,1)
    assert queue.recent()[0]['processed']==0


def test_crash_retries_are_bounded(queue):
    queue.enqueue('acme')
    for i in range(3):
        assert queue.claim()
        with queue.store.connect() as conn:
            conn.execute("UPDATE import_runs SET lease_until=now()-interval '1 second'")
    assert queue.claim() is None
    assert queue.recent()[0]['state']=='failed' and queue.recent()[0]['failures']==3


def test_cursor_and_job_writes_rollback_together(queue):
    queue.enqueue('acme'); run=queue.claim(); queue.set_snapshot(run,jobs(1))
    def rollback(conn):
        queue.checkpoint(conn,run,1)
        raise RuntimeError('Simulated database rollback')
    with pytest.raises(RuntimeError):
        queue.store.upsert_jobs(jobs(1),'greenhouse:acme','Acme',False,transaction_hook=rollback)
    assert queue.store.status()['jobs']==0
    assert queue.recent()[0]['processed']==0 and queue.recent()[0]['state']=='running'


def test_legacy_import_cannot_race_queued_source(queue):
    queue.enqueue('acme')
    with pytest.raises(ValueError,match='durable import'):
        queue.store.upsert_jobs(jobs(1),'greenhouse:acme','Acme',False)
    assert queue.store.status()['jobs']==0


def test_job_budget_defers_without_closing_or_losing_progress(queue,monkeypatch):
    monkeypatch.setenv('DAILY_IMPORT_JOB_LIMIT','5')
    monkeypatch.setattr('rolecraft.worker.fetch_board',lambda *_:(jobs(),7,True))
    queue.enqueue('acme'); tick(queue); tick(queue)
    result=queue.recent()[0]
    assert result['processed']==5 and result['state']=='retry' and result['failures']==0
    assert result['error_code']=='daily_budget'
    with queue.store.connect() as conn:
        assert conn.execute("SELECT used FROM usage_buckets WHERE kind='import_jobs'").fetchone()['used']==5
        assert conn.execute('SELECT snapshot FROM import_runs').fetchone()['snapshot']


def test_failure_limit_and_safe_error_codes(queue,monkeypatch):
    def fail(*_): raise RuntimeError('SECRET-CONNECTION-STRING')
    monkeypatch.setattr('rolecraft.worker.fetch_board',fail)
    queue.enqueue('acme')
    for i in range(3):
        tick(queue); due(queue)
    result=queue.recent()[0]
    assert result['state']=='failed' and result['failures']==3
    assert 'SECRET' not in str(result)


def test_pruning_only_removes_terminal_history(queue):
    old,_=queue.enqueue('old'); queue.cancel(old['id'])
    queue.enqueue('active')
    with queue.store.connect() as conn:
        conn.execute("UPDATE import_runs SET finished_at=now()-interval '10 days' WHERE id=%s",(old['id'],))
    assert queue.prune(7)==1
    assert len(queue.recent())==1 and queue.recent()[0]['board']=='active'


def test_operator_api_and_readiness_contracts(queue,monkeypatch):
    from app import app
    client=TestClient(app)
    admin={'Authorization':'Bearer '+os.environ['INGEST_TOKEN']}
    user={'Authorization':'Bearer '+os.environ['APP_ACCESS_TOKEN']}
    assert client.get('/api/operations').status_code==401
    assert client.get('/api/operations',headers=user).status_code==401
    assert client.get('/api/readiness',headers=user).status_code==503  # empty real corpus
    response=client.post('/api/import-runs',json={'board':'acme'},headers=admin)
    assert response.status_code==202 and response.json()['created']
    assert client.post('/api/import-runs',json={'board':'acme'},headers=admin).status_code==200
    assert client.post('/api/import-runs',json={'board':'another'},headers=user).status_code==401
    identifier=response.json()['run']['id']
    assert client.delete('/api/import-runs/'+identifier,headers=admin).status_code==200
    assert client.delete('/api/import-runs/'+identifier,headers=admin).status_code==409
    assert client.delete('/api/import-runs/not-a-uuid',headers=admin).status_code==422
    text=client.get('/api/operations',headers=admin).text
    assert 'lease_token' not in text and os.environ['INGEST_TOKEN'] not in text
    assert os.environ['DATABASE_URL'] not in text
    queue.store.upsert_jobs(jobs(1),'greenhouse:acme','Acme',False)
    ready=client.get('/api/readiness',headers=user)
    assert ready.status_code==200 and ready.json()['provider_health']=='not_probed'


def test_expired_snapshot_is_not_reconciled(queue,monkeypatch):
    queue.enqueue('acme'); run=queue.claim(); queue.set_snapshot(run,jobs(1))
    with queue.store.connect() as conn:
        conn.execute("UPDATE import_runs SET state='queued',lease_token=NULL,lease_until=NULL,snapshot_at=now()-interval '2 days'")
    monkeypatch.setattr('rolecraft.worker.fetch_board',lambda *_:pytest.fail('Must not fetch over existing snapshot'))
    tick(queue)
    assert queue.recent()[0]['state']=='failed' and queue.store.status()['jobs']==0
