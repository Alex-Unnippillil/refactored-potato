"""Schedule invariants against disposable PostgreSQL; no paid providers."""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import app
from rolecraft.import_queue import ImportQueue, QueueBudget, QueueConflict
from rolecraft.models import Filters, Job, utcnow
from rolecraft.schedules import SourceSchedules, ScheduleMissing, scheduler_enabled, validate_config
from rolecraft.store import demo_store
from rolecraft.worker import tick


def sample_jobs(n=1, board='acme'):
    template = dict(demo_store().jobs[0])
    template.update(company=board, source_key='greenhouse:'+board, source='Greenhouse',
                    is_demo=False, first_seen=utcnow(), last_seen=utcnow())
    return [Job.model_validate({**template, 'id': f'gh-{board}-{i}',
                               'source_url': f'https://example.com/jobs/{board}/{i}'}) for i in range(n)]


@pytest.fixture
def schedules(monkeypatch):
    if not os.getenv('TEST_DATABASE_URL'):
        pytest.skip('Needs a disposable PostgreSQL/pgvector database')
    import psycopg
    monkeypatch.setenv('DATABASE_URL', os.environ['TEST_DATABASE_URL'])
    monkeypatch.setenv('APP_ACCESS_TOKEN', 'workspace-test-'+'a'*32)
    monkeypatch.setenv('INGEST_TOKEN', 'operator-test-'+'b'*32)
    monkeypatch.setenv('OPENAI_API_KEY', 'test-only-not-real')
    monkeypatch.setenv('DAILY_IMPORT_JOB_LIMIT', '200')
    monkeypatch.delenv('IMPORT_SCHEDULER_ENABLED', raising=False)
    monkeypatch.delenv('OPENAI_EMBEDDING_MODEL', raising=False)
    monkeypatch.setattr('rolecraft.providers.embed', lambda texts: [[1.0]+[0.0]*1535 for _ in texts])
    with psycopg.connect(os.environ['TEST_DATABASE_URL'], autocommit=True) as conn:
        for migration in sorted((Path(__file__).resolve().parents[1]/'sql').glob('*.sql')):
            conn.execute(migration.read_text())
        conn.execute('TRUNCATE source_schedules,import_runs,worker_heartbeat,jobs,job_chunks,sources,usage_buckets CASCADE')
    return SourceSchedules()


@pytest.mark.parametrize('value', ['', '0', 'false', 'TRUEE', 'yes'])
def test_scheduler_is_explicitly_opt_in(monkeypatch, value):
    monkeypatch.setenv('IMPORT_SCHEDULER_ENABLED', value)
    assert not scheduler_enabled()


@pytest.mark.parametrize('value', ['1', 'true', 'TRUE', ' true '])
def test_scheduler_explicit_enable(monkeypatch, value):
    monkeypatch.setenv('IMPORT_SCHEDULER_ENABLED', value)
    assert scheduler_enabled()


@pytest.mark.parametrize('interval', [0, 5, 169, True, '24', 24.5])
def test_invalid_interval(interval):
    with pytest.raises(ValueError):
        validate_config(interval, False)


def test_paused_by_default_and_normalized(schedules):
    row = schedules.create('ACME')
    assert row['board']=='acme' and row['enabled'] is False and row['revision']==1
    assert schedules.dispatch_due() is None
    assert schedules.queue.recent()==[]


def test_update_revision_and_resume(schedules):
    row = schedules.create('acme')
    changed = schedules.update('acme', 12, True, row['revision'])
    assert changed['revision']==2 and changed['enabled'] and changed['interval_hours']==12
    with pytest.raises(QueueConflict, match='another session'):
        schedules.update('acme', 24, False, 1)
    assert schedules.dispatch_due()['created']


def test_interval_edit_restarts_cadence_without_instant_import(schedules):
    schedules.create('acme', enabled=True)
    row = schedules.update('acme', 12, True, 1)
    assert row['next_run_at'] > row['updated_at']
    assert schedules.dispatch_due() is None


def test_parallel_schedule_creation(schedules):
    def create(_):
        try:
            return SourceSchedules().create('same')['board']
        except QueueConflict:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(create, range(4)))
    assert results.count('same')==1


def test_schedule_limit_and_duplicate(schedules):
    for i in range(20):
        schedules.create(f'board-{i}')
    with pytest.raises(QueueConflict):
        schedules.create('overflow')
    with pytest.raises(QueueConflict):
        schedules.create('board-0')


def test_concurrent_dispatch_admits_once(schedules):
    schedules.create('acme', enabled=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _: SourceSchedules().dispatch_due(), range(4)))
    assert sum(bool(result and result['created']) for result in results)==1
    assert len(schedules.queue.recent())==1
    assert schedules.overview()['budgets']['queue_requests']['used']==1


def test_dispatch_skips_locked_schedule(schedules):
    schedules.create('a', enabled=True)
    schedules.create('b', enabled=True)
    with schedules.store.connect() as held:
        held.execute("SELECT board FROM source_schedules WHERE board='a' FOR UPDATE")
        assert schedules.dispatch_due()['board']=='b'


def test_long_downtime_coalesces_to_one_run(schedules):
    schedules.create('acme', enabled=True)
    with schedules.store.connect() as conn:
        conn.execute("UPDATE source_schedules SET next_run_at=now()-interval '60 days'")
    assert schedules.dispatch_due()['created']
    assert schedules.dispatch_due() is None
    assert len(schedules.queue.recent())==1


def test_active_manual_run_is_reused_without_budget(schedules):
    original, _ = schedules.queue.enqueue('acme')
    schedules.create('acme', enabled=True)
    result=schedules.dispatch_due()
    assert result['status']=='active' and not result['created']
    view=schedules.overview()
    assert view['schedules'][0]['last_run_id']==original['id']
    assert view['budgets']['queue_requests']['used']==1
    assert schedules.dispatch_due() is None


def test_admission_budget_defers_without_a_run(schedules):
    for i in range(10):
        schedules.queue.enqueue(f'job-{i}')
    schedules.create('acme', enabled=True)
    assert schedules.dispatch_due()['status']=='daily_budget'
    assert len(schedules.queue.recent())==10
    row=schedules.overview()['schedules'][0]
    assert row['last_run_id'] is None and row['next_run_at'].hour==0
    assert row['next_run_at'].utcoffset().total_seconds()==0
    assert schedules.dispatch_due() is None


def test_full_queue_has_cooldown(schedules):
    with schedules.store.connect() as conn:
        for i in range(20):
            conn.execute('INSERT INTO import_runs(id,board) VALUES(%s,%s)',(f'id-{i}',f'board-{i}'))
    schedules.create('acme', enabled=True)
    assert schedules.dispatch_due()['status']=='queue_full'
    assert schedules.dispatch_due() is None
    assert schedules.overview()['budgets']['queue_requests']['used']==0


def test_admission_and_deadline_are_atomic(schedules, monkeypatch):
    schedules.create('acme', enabled=True)
    original=schedules.queue.enqueue_in_transaction
    def crash(conn, board):
        original(conn, board)
        raise RuntimeError('crash before deadline write')
    monkeypatch.setattr(schedules.queue,'enqueue_in_transaction',crash)
    with pytest.raises(RuntimeError):
        schedules.dispatch_due()
    assert schedules.queue.recent()==[]
    row=schedules.overview()['schedules'][0]
    assert row['dispatch_status']=='never' and row['last_run_id'] is None
    assert schedules.overview()['budgets']['queue_requests']['used']==0
    monkeypatch.setattr(schedules.queue,'enqueue_in_transaction',original)
    assert schedules.dispatch_due()['created']


def test_pause_and_remove_preserve_admitted_run_and_jobs(schedules, monkeypatch):
    schedules.create('acme', enabled=True)
    schedules.dispatch_due()
    row=schedules.update('acme',24,False,1)
    monkeypatch.setattr('rolecraft.worker.fetch_board', lambda *_: (sample_jobs(),1,True))
    tick(schedules.queue)
    assert schedules.queue.recent()[0]['state']=='succeeded'
    schedules.remove('acme',row['revision'])
    assert schedules.queue.store.status()['jobs']==1 and len(schedules.queue.recent())==1
    assert schedules.overview()['schedules']==[]


def test_manual_run_on_paused_schedule_and_repeated_click(schedules):
    schedules.create('acme')
    run, created = schedules.run_now('acme',1)
    again, new = schedules.run_now('acme',1)
    assert created and not new and run['id']==again['id']
    assert schedules.overview()['schedules'][0]['enabled'] is False
    with pytest.raises(QueueConflict):
        schedules.run_now('acme',2)


def test_missing_and_stale_remove(schedules):
    with pytest.raises(ScheduleMissing):
        schedules.update('absent',24,True,1)
    schedules.create('acme')
    with pytest.raises(QueueConflict):
        schedules.remove('acme',2)
    assert len(schedules.overview()['schedules'])==1


def test_pruning_keeps_schedule_and_clears_foreign_key(schedules):
    schedules.create('acme')
    run, _ = schedules.run_now('acme',1)
    schedules.queue.cancel(run['id'])
    with schedules.store.connect() as conn:
        conn.execute("UPDATE import_runs SET finished_at=now()-interval '9 days'")
    assert schedules.queue.prune(7)==1
    assert schedules.overview()['schedules'][0]['last_run_id'] is None


def test_source_freshness_matches_retrieval(schedules, monkeypatch):
    schedules.create('acme')
    schedules.store.upsert_jobs(sample_jobs(4),'greenhouse:acme','Acme',False)
    with schedules.store.connect() as conn:
        conn.execute("UPDATE jobs SET last_seen=now()-interval '20 days' WHERE id='gh-acme-1'")
        conn.execute("UPDATE jobs SET expires_at=now()-interval '1 hour' WHERE id='gh-acme-2'")
        conn.execute("UPDATE jobs SET active=false WHERE id='gh-acme-3'")
    row=schedules.overview()['schedules'][0]
    assert row['active_roles']==3 and row['searchable_roles']==1
    assert schedules.store.retrieve('',Filters())['eligible_count']==1
    monkeypatch.setenv('SOURCE_FRESH_DAYS','30')
    assert schedules.overview()['schedules'][0]['searchable_roles']==2


def test_worker_opt_in_does_not_dispatch_by_default(schedules,monkeypatch):
    schedules.create('acme',enabled=True)
    assert tick(schedules.queue) is False
    monkeypatch.setattr('rolecraft.worker.fetch_board',lambda *_:(sample_jobs(),1,True))
    assert tick(schedules.queue,schedule=True)
    assert schedules.queue.recent()[0]['state']=='succeeded'
    view=schedules.overview()
    assert view['scheduler']['worker']['recent']
    assert view['schedules'][0]['last_retained_success_at'] is not None


def test_scheduler_failure_does_not_starve_existing_queue(schedules,monkeypatch):
    schedules.queue.enqueue('acme')
    monkeypatch.setattr('rolecraft.worker.fetch_board',lambda *_:(sample_jobs(),1,True))
    with patch.object(SourceSchedules,'dispatch_due',side_effect=RuntimeError('redacted')):
        assert tick(schedules.queue,schedule=True)
    assert schedules.queue.recent()[0]['state']=='succeeded'


def test_schedule_api_auth_validation_and_conflict(schedules):
    client=TestClient(app)
    admin={'Authorization':'Bearer '+os.environ['INGEST_TOKEN']}
    user={'Authorization':'Bearer '+os.environ['APP_ACCESS_TOKEN']}
    assert client.post('/api/source-schedules',json={'board':'acme'},headers=user).status_code==401
    response=client.post('/api/source-schedules',json={'board':'acme'},headers=admin)
    assert response.status_code==201 and not response.json()['schedule']['enabled']
    assert client.post('/api/source-schedules',json={'board':'acme'},headers=admin).status_code==409
    assert client.put('/api/source-schedules/acme',json={'interval_hours':12,'enabled':True,'expected_revision':1},headers=admin).status_code==200
    assert client.put('/api/source-schedules/acme',json={'interval_hours':24,'enabled':False,'expected_revision':1},headers=admin).status_code==409
    for value in (5,169,'24',True):
        assert client.post('/api/source-schedules',json={'board':'other','interval_hours':value},headers=admin).status_code==422
    for payload in ({'board':'../escape'}, {'board':'valid','enabled':'true'}, {'board':'valid','url':'https://evil.invalid'}):
        assert client.post('/api/source-schedules',json=payload,headers=admin).status_code==422
    assert client.post('/api/source-schedules/acme/run',json={'expected_revision':2},headers=admin).status_code==202
    assert client.post('/api/source-schedules/acme/run',json={'expected_revision':2},headers=admin).status_code==200
    assert client.delete('/api/source-schedules/acme?expected_revision=1',headers=admin).status_code==409
    assert client.delete('/api/source-schedules/acme?expected_revision=2',headers=admin).status_code==200
    assert client.delete('/api/source-schedules/acme?expected_revision=2',headers=admin).status_code==404
    assert len(schedules.queue.recent())==1


def test_configure_without_paid_credentials_but_run_requires_them(schedules,monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY')
    client=TestClient(app)
    admin={'Authorization':'Bearer '+os.environ['INGEST_TOKEN']}
    assert client.post('/api/source-schedules',json={'board':'acme'},headers=admin).status_code==201
    assert client.post('/api/source-schedules/acme/run',json={'expected_revision':1},headers=admin).status_code==503


def test_api_never_exposes_snapshot_or_worker_lease(schedules):
    schedules.create('acme',enabled=True); schedules.dispatch_due()
    run=schedules.queue.claim(); schedules.queue.set_snapshot(run,sample_jobs())
    client=TestClient(app)
    response=client.get('/api/operations',headers={'Authorization':'Bearer '+os.environ['INGEST_TOKEN']})
    assert response.status_code==200 and response.json()['can_schedule']
    for secret in ('lease_token','snapshot',os.environ['INGEST_TOKEN'],os.environ['DATABASE_URL'],os.environ['OPENAI_API_KEY']):
        assert secret not in response.text


def test_demo_has_no_schedules_or_simulated_budget(monkeypatch):
    monkeypatch.delenv('DATABASE_URL',raising=False)
    monkeypatch.delenv('APP_ACCESS_TOKEN',raising=False)
    monkeypatch.setenv('INGEST_TOKEN','x'*32)
    client=TestClient(app)
    result=client.get('/api/operations').json()
    assert result['schedules']==[] and result['budgets'] is None and not result['can_schedule']
    assert result['scheduler']=={'configured':False,'worker':None}
    headers={'Authorization':'Bearer '+'x'*32}
    assert client.post('/api/source-schedules',json={'board':'acme'},headers=headers).status_code==503
