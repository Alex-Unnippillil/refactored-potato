import importlib
import json

import pytest
from fastapi.testclient import TestClient

module=importlib.import_module('app')


@pytest.fixture
def client(monkeypatch):
    for key in ('DATABASE_URL','APP_ACCESS_TOKEN','INGEST_TOKEN','OPENAI_API_KEY','OPENAI_CHAT_MODEL','COHERE_API_KEY'):
        monkeypatch.delenv(key,raising=False)
    return TestClient(module.app)


@pytest.mark.parametrize('path',['/','/app.js','/styles.css','/icon.svg','/api/health','/api/status'])
def test_routes_and_security_headers(client,path):
    response=client.get(path)
    assert response.status_code==200
    assert "script-src 'self'" in response.headers['content-security-policy']
    assert response.headers['x-content-type-options']=='nosniff'
    assert response.headers['x-frame-options']=='DENY'
    if path.startswith('/api/'):assert response.headers['cache-control']=='no-store'


def test_api_search_and_citations(client):
    result=client.post('/api/search',json={'query':'calm python','preferences':['async']})
    assert result.status_code==200
    assert result.json()['mode']=='demo'
    assert result.json()['jobs']
    assert all(e['quote'] in j['description'] for j in result.json()['jobs'] for e in j['evidence'])


def test_brief_is_honest_and_extractive(client):
    response=client.post('/api/brief',json={'query':'AI learning'})
    assert response.status_code==200
    assert response.json()['method']=='Extractive brief · no generative model'
    assert len(response.json()['cards'])==3


def test_invalid_api_input_returns_422(client):
    assert client.post('/api/search',json={'filters':{'min_salary':-1}}).status_code==422


def test_request_body_limit_includes_actual_bytes(client):
    assert client.post('/api/search',content=b'x'*256001,headers={'Content-Type':'application/json'}).status_code==413


def test_ingestion_disabled_without_operator_token(client):
    assert client.post('/api/ingest',json={'provider':'greenhouse','board':'test'}).status_code==503


def test_ingest_token_not_workspace_token(client,monkeypatch):
    monkeypatch.setenv('INGEST_TOKEN','a'*32)
    monkeypatch.setenv('APP_ACCESS_TOKEN','b'*32)
    response=client.post('/api/ingest',json={'provider':'greenhouse','board':'test'},headers={'Authorization':'Bearer '+'b'*32})
    assert response.status_code==401


def test_protected_workspace_requires_bearer(client,monkeypatch):
    monkeypatch.setenv('APP_ACCESS_TOKEN','x'*32)
    assert client.post('/api/search',json={}).status_code==401
    assert client.post('/api/search',json={},headers={'Authorization':'Bearer '+'x'*32}).status_code==200
    assert client.get('/api/status').json()['requires_access'] is True


def test_live_database_failure_never_falls_back_to_demo(client,monkeypatch):
    monkeypatch.setenv('DATABASE_URL','postgresql://example.invalid/db')
    monkeypatch.setenv('APP_ACCESS_TOKEN','x'*32)
    class BrokenStore:
        def retrieve(self,*a,**k):raise RuntimeError('secret-database-url')
    monkeypatch.setattr(module,'get_store',lambda:BrokenStore())
    response=client.post('/api/search',json={},headers={'Authorization':'Bearer '+'x'*32})
    assert response.status_code==503
    assert 'secret-database-url' not in response.text
    assert 'No demo fallback' in response.text


def test_status_never_contains_secrets(client,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','sensitive-key')
    assert 'sensitive-key' not in client.get('/api/status').text
    assert client.get('/api/status').json()['mode']=='demo'


def test_lookup_empty_and_known_ids(client):
    assert client.post('/api/jobs',json={'ids':[]}).json()['jobs']==[]
    assert len(client.post('/api/jobs',json={'ids':['demo-01']}).json()['jobs'])==1


def test_no_cors_grants_untrusted_origin(client):
    response=client.post('/api/search',json={},headers={'Origin':'https://untrusted.example'})
    assert 'access-control-allow-origin' not in response.headers
