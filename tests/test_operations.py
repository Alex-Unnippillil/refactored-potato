import os

import pytest
from fastapi.testclient import TestClient

from app import app
from rolecraft.operations import readiness, release_info


@pytest.fixture
def client(monkeypatch):
    for name in ('DATABASE_URL','APP_ACCESS_TOKEN','INGEST_TOKEN','OPENAI_API_KEY','VERCEL_GIT_COMMIT_SHA','ROLECRAFT_COMMIT'):
        monkeypatch.delenv(name,raising=False)
    return TestClient(app)


@pytest.mark.parametrize('path',['/operations','/operations.css','/operations.js','/api/readiness','/api/operations'])
def test_operations_routes_security_headers(client,path):
    response=client.get(path)
    assert response.status_code==200
    assert response.headers['x-frame-options']=='DENY'
    assert "script-src 'self'" in response.headers['content-security-policy']
    if path.startswith('/api/'):
        assert response.headers['cache-control']=='no-store'


def test_demo_operations_are_real_not_fake_activity(client):
    data=client.get('/api/operations').json()
    assert data['stats']['jobs']==24 and data['runs']==[] and data['worker'] is None
    assert data['mode']=='demo' and data['can_enqueue'] is False and data['ingestion_ready'] is False
    assert data['provider_health']=='not_probed'


def test_demo_cannot_queue_or_cancel(client,monkeypatch):
    monkeypatch.setenv('INGEST_TOKEN','x'*32)
    headers={'Authorization':'Bearer '+'x'*32}
    assert client.post('/api/import-runs',json={'board':'test'},headers=headers).status_code==503
    assert client.delete('/api/import-runs/00000000-0000-0000-0000-000000000000',headers=headers).status_code==503


def test_bad_board_and_unknown_fields_rejected(client):
    assert client.post('/api/import-runs',json={'board':'https://evil.example'}).status_code==422
    assert client.post('/api/import-runs',json={'board':'ok','url':'https://evil.example'}).status_code==422


def test_status_never_calls_provider(client,monkeypatch):
    monkeypatch.setattr('rolecraft.providers.embed',lambda *_:pytest.fail('Readiness made a paid provider call'))
    assert client.get('/api/readiness').status_code==200


def test_readiness_fails_closed_without_leaking_exception(client,monkeypatch):
    monkeypatch.setenv('DATABASE_URL','postgresql://fake:SECRET@example.invalid/db')
    monkeypatch.setenv('APP_ACCESS_TOKEN','x'*32)
    class Broken:
        def connect(self): raise RuntimeError('SECRET DRIVER DETAILS')
    monkeypatch.setattr('rolecraft.operations.get_store',lambda:Broken())
    assert client.get('/api/readiness').status_code==401
    r=client.get('/api/readiness',headers={'Authorization':'Bearer '+'x'*32})
    assert r.status_code==503 and r.json()['mode']=='live'
    assert 'SECRET' not in r.text and r.json()['stats'] is None


def test_release_sha_is_sanitized(client,monkeypatch):
    monkeypatch.setenv('ROLECRAFT_COMMIT','<script>secret</script>')
    assert release_info()['commit']=='local'
    monkeypatch.setenv('ROLECRAFT_COMMIT','a'*40)
    assert release_info()['commit']=='a'*12


def test_same_tokens_are_rejected_for_queue(client,monkeypatch):
    for name in ('APP_ACCESS_TOKEN','INGEST_TOKEN'):monkeypatch.setenv(name,'x'*32)
    monkeypatch.setenv('DATABASE_URL','test')
    monkeypatch.setenv('OPENAI_API_KEY','test')
    response=client.post('/api/import-runs',json={'board':'acme'},headers={'Authorization':'Bearer '+'x'*32})
    assert response.status_code==503 and 'different' in response.text


def test_protected_demo_status_needs_access(client,monkeypatch):
    monkeypatch.setenv('APP_ACCESS_TOKEN','x'*32)
    assert client.get('/api/operations').status_code==401
    assert client.get('/api/operations',headers={'Authorization':'Bearer '+'x'*32}).status_code==200
