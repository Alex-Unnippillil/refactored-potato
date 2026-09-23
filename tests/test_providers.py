import socket

import pytest

from rolecraft import brief, ingest, providers
from rolecraft.models import SearchRequest
from rolecraft.store import demo_store


def test_embedding_dimension_and_index_validation(monkeypatch):
    monkeypatch.setattr(providers,'provider_json',lambda *a,**k:{'data':[{'index':0,'embedding':[0.1]*1536}]})
    assert len(providers.embed(['hello'])[0])==1536
    monkeypatch.setattr(providers,'provider_json',lambda *a,**k:{'data':[{'index':1,'embedding':[0.1]*1536}]})
    with pytest.raises(providers.ProviderError):providers.embed(['hello'])
    monkeypatch.setattr(providers,'provider_json',lambda *a,**k:{'data':[{'index':0,'embedding':[0.1]*256}]})
    with pytest.raises(providers.ProviderError):providers.embed(['hello'])


def test_embedding_model_mismatch_fails_closed(monkeypatch):
    monkeypatch.setenv('OPENAI_EMBEDDING_MODEL','another-model')
    with pytest.raises(providers.ProviderError):providers.embed(['query'])


def test_non_finite_vectors_rejected(monkeypatch):
    monkeypatch.setattr(providers,'provider_json',lambda *a,**k:{'data':[{'index':0,'embedding':[float('nan')]*1536}]})
    with pytest.raises(providers.ProviderError):providers.embed(['query'])


def test_optional_reranker_validates_complete_permutation(monkeypatch):
    monkeypatch.setenv('COHERE_API_KEY','test')
    monkeypatch.setattr(providers,'provider_json',lambda *a,**k:{'results':[{'index':1},{'index':0}]})
    assert providers.rerank('query',['one','two'])==[1,0]
    monkeypatch.setattr(providers,'provider_json',lambda *a,**k:{'results':[{'index':0},{'index':0}]})
    with pytest.raises(providers.ProviderError):providers.rerank('query',['one','two'])


@pytest.mark.parametrize('url',['http://careers.example.org/job','https://127.0.0.1/job','https://careers.example.org:8443/job','https://user:pass@careers.example.org/job','https://not-approved.example.org/job'])
def test_scrape_rejects_unapproved_targets(url,monkeypatch):
    monkeypatch.setenv('SCRAPE_ALLOWED_HOSTS','careers.example.org')
    with pytest.raises(ValueError):ingest.safe_scrape_url(url)


@pytest.mark.parametrize('address',['127.0.0.1','10.0.0.1','169.254.169.254','::1','192.168.1.1'])
def test_scrape_rejects_private_dns_results(address,monkeypatch):
    monkeypatch.setenv('SCRAPE_ALLOWED_HOSTS','careers.example.org')
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',(address,443))])
    with pytest.raises(ValueError):ingest.safe_scrape_url('https://careers.example.org/job')


def test_scrape_allows_explicit_public_host(monkeypatch):
    monkeypatch.setenv('SCRAPE_ALLOWED_HOSTS','careers.example.org')
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443))])
    assert ingest.safe_scrape_url('https://careers.example.org/job').endswith('/job')


@pytest.mark.parametrize('token',['../admin','https://example.org','board?x=1','board#frag'])
def test_greenhouse_token_validation_precedes_network(token):
    with pytest.raises(ValueError):ingest.fetch_board(token)


def test_ai_cannot_invent_citations(monkeypatch):
    class LiveDemo:
        mode='live'
        def retrieve(self,*a,**k):return demo_store().retrieve(*a,**k)
    monkeypatch.setenv('OPENAI_CHAT_MODEL','test-model')
    monkeypatch.delenv('COHERE_API_KEY',raising=False)
    monkeypatch.setattr(brief,'provider_json',lambda *a,**k:{'choices':[{'message':{'content':'{"selections":[{"job_id":"invented","quote":"Unsupported claim that was never in any source."}]}'}}]})
    result=brief.make_brief(SearchRequest(query='backend calm'),LiveDemo())
    assert result['method']=='Extractive brief · no generative model'
    assert result['warning']
    assert all(c['id']!='invented' for c in result['cards'])
