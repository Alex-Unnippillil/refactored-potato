"""Source-evidence and graceful degradation regression cases; no paid calls."""
import math

import pytest

from rolecraft.brief import make_brief
from rolecraft.models import Filters, SearchRequest
from rolecraft.providers import ProviderError, ProviderUnavailable
from rolecraft import providers
from rolecraft.search import fuse, search
from rolecraft.signals import assess_preferences, excerpts
from rolecraft.store import demo_store


@pytest.mark.parametrize('text,key,status', [
    ('We provide mentorship and a dedicated mentor.', 'mentorship', 'supporting'),
    ('We do not provide mentorship.', 'mentorship', 'conflicting'),
    ('No mentorship is offered.', 'mentorship', 'conflicting'),
    ('Mentorship is not available.', 'mentorship', 'conflicting'),
    ('We may offer mentorship later.', 'mentorship', 'uncertain'),
    ('Mentorship is planned.', 'mentorship', 'uncertain'),
    ('We cannot guarantee mentorship.', 'mentorship', 'uncertain'),
    ('We cannot guarantee a learning budget.', 'learning', 'uncertain'),
    ('Mentorship is not guaranteed.', 'mentorship', 'uncertain'),
    ('We offer mentorship. Other departments provide no mentorship.', 'mentorship', 'mixed'),
    ('We hire junior engineers at a high-growth company.', 'mentorship', 'not_found'),
    ('Join a high-growth company.', 'learning', 'not_found'),
    ('We offer a learning budget.', 'learning', 'supporting'),
    ('We offer no learning budget.', 'learning', 'conflicting'),
    ('We plan to offer a learning budget.', 'learning', 'uncertain'),
    ('We protect a sustainable pace.', 'balance', 'supporting'),
    ('Regular weekend work and mandatory overtime.', 'balance', 'conflicting'),
    ('No on-call rotation is required.', 'balance', 'supporting'),
    ('We are not asynchronous; we provide mentorship.', 'async', 'conflicting'),
    ('We are not asynchronous; we provide mentorship.', 'mentorship', 'supporting'),
    ('We are not asynchronous but provide mentorship.', 'mentorship', 'supporting'),
    ('We not only provide mentorship but also coaching.', 'mentorship', 'supporting'),
    ('We have a small team.', 'ownership', 'not_found'),
    ('You have autonomy to choose the technical direction.', 'ownership', 'supporting'),
    ('We have limited autonomy.', 'ownership', 'conflicting'),
    ('We are a mission-driven clean energy organization.', 'mission', 'supporting'),
    ('We have no sustainability commitment.', 'mission', 'conflicting'),
])
def test_source_evidence_states(text, key, status):
    item = assess_preferences(text, [key])[0]
    assert item['status'] == status
    for excerpt in item['excerpts']:
        assert text[excerpt['start']:excerpt['end']] == excerpt['quote']
        assert len(excerpt['quote']) <= 500


def test_long_unicode_evidence_keeps_the_relevant_exact_span():
    text = '🌿 ' + 'Introductory material ' * 70 + 'We do not provide mentorship in this team'
    item = assess_preferences(text, ['mentorship'])[0]
    assert item['status'] == 'conflicting'
    quote = item['excerpts'][0]
    assert 'not provide mentorship' in quote['quote']
    assert text[quote['start']:quote['end']] == quote['quote']


def test_unselected_free_text_does_not_create_preference_claims():
    result = search(SearchRequest(query='no mentorship', semantic_weight=0))
    assert all(not j['preference_assessments'] for j in result['jobs'])


def test_conflicting_excerpt_is_prioritized_and_never_bonused():
    description = 'We provide mentorship, asynchronous work and ownership. We have mandatory overtime.'
    assessments = assess_preferences(description, ['mentorship', 'async', 'ownership', 'balance'])
    assert excerpts(description, '', assessments)[0]['polarity'] == 'conflict'
    class ConflictingStore:
        mode = 'demo'
        def retrieve(self, *args, **kwargs):
            job = dict(demo_store().jobs[0], description=description)
            return {'jobs': [job], 'lexical': [(job['id'], 1)], 'semantic': [], 'eligible_count': 1}
    job = search(SearchRequest(preferences=['balance'], semantic_weight=0), ConflictingStore())['jobs'][0]
    assert job['retrieval_explanation']['preference_adjustment'] < 0
    assert job['fit'] == 'Conflicting preference text'
    assert job['unconfirmed_preferences'] == ['Sustainable pace']


class OutageStore:
    mode = 'live'
    def __init__(self, error=None):
        self.calls = []
        self.error = error or ProviderUnavailable('Transport failure.')
    def retrieve(self, query, filters, semantic=True):
        self.calls.append((query, filters.model_dump(), semantic))
        if semantic:
            raise self.error
        return demo_store().retrieve(query, filters, semantic=False)


@pytest.fixture(autouse=True)
def no_optional_provider_calls(monkeypatch):
    monkeypatch.delenv('COHERE_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_CHAT_MODEL', raising=False)


def test_hybrid_degrades_explicitly_without_relaxing_filters():
    store = OutageStore()
    request = SearchRequest(query='Python', filters=Filters(country='Canada', work_mode='Remote', min_salary=140000))
    result = search(request, store)
    assert result['jobs'] and result['mode'] == 'live'
    assert result['retrieval_status'] == 'keyword_fallback' and result['warnings']
    assert result['trace']['semantic_weight'] == 0
    assert result['trace']['requested_semantic_weight'] == .65
    assert result['trace']['semantic_candidates'] == 0
    assert len(store.calls) == 2 and store.calls[0][:2] == store.calls[1][:2]
    for job in result['jobs']:
        assert job['country'] == 'Canada' and job['work_mode'] == 'Remote'
        assert job['salary_min'] >= 140000 and job['currency'] == 'CAD'
        assert job['retrieval_explanation']['semantic_rank'] is None
        assert math.isclose(job['scores']['rrf'], 1 / (60 + job['retrieval_explanation']['keyword_rank']), abs_tol=1e-7)


@pytest.mark.parametrize('payload', [SearchRequest(query='Python', semantic_weight=1),
                                     SearchRequest(query='Python', allow_keyword_fallback=False)])
def test_meaning_only_and_strict_requests_do_not_degrade(payload):
    store = OutageStore()
    with pytest.raises(ProviderUnavailable):
        search(payload, store)
    assert len(store.calls) == 1


@pytest.mark.parametrize('error', [ProviderError('Bad configuration.'), RuntimeError('Database unavailable.')])
def test_non_transient_failures_never_fallback(error):
    store = OutageStore(error)
    with pytest.raises(type(error)):
        search(SearchRequest(query='Python'), store)
    assert len(store.calls) == 1


def test_keyword_only_does_not_call_semantic_provider():
    store = OutageStore()
    result = search(SearchRequest(query='Python', semantic_weight=0), store)
    assert result['jobs'] and not result['warnings']
    assert store.calls[0][2] is False and len(store.calls) == 1
    assert result['trace']['embedding'] == 'Not used for this request'


def test_brief_preserves_degradation_warning():
    result = make_brief(SearchRequest(query='Python'), OutageStore())
    assert result['cards'] and 'keyword-only' in result['warning']
    assert result['retrieval_status'] == 'keyword_fallback'


def test_fusion_does_not_double_count_one_branch():
    assert fuse([('a', 1), ('a', 1)], [], 0) == {'a': 1 / 61}


@pytest.mark.parametrize('vector', [[0] * 1536, [True] * 1536, [float('inf')] * 1536,
                                   [10**1000] * 1536, ['0.2'] * 1536, None])
def test_invalid_embedding_values_fail_closed(vector, monkeypatch):
    monkeypatch.setattr(providers, 'provider_json', lambda *a, **k: {'data': [{'index': 0, 'embedding': vector}]})
    with pytest.raises(ProviderError) as exc:
        providers.embed(['hello'])
    assert not isinstance(exc.value, ProviderUnavailable)


@pytest.mark.parametrize('index', [True, '0', 0.0, -1, None])
def test_embedding_indices_require_real_integers(index, monkeypatch):
    monkeypatch.setattr(providers, 'provider_json', lambda *a, **k: {'data': [{'index': index, 'embedding': [.1] * 1536}]})
    with pytest.raises(ProviderError):
        providers.embed(['hello'])


@pytest.mark.parametrize('index', [True, '0', 0.9, 0.0, None])
def test_reranker_indices_are_not_coerced(index, monkeypatch):
    monkeypatch.setenv('COHERE_API_KEY', 'test-only')
    monkeypatch.setattr(providers, 'provider_json', lambda *a, **k: {'results': [{'index': index}]})
    with pytest.raises(ProviderError):
        providers.rerank('hello', ['document'])


@pytest.mark.parametrize('status,transient,calls', [(429,True,2),(503,True,2),(500,True,1),(401,False,1),(403,False,1)])
def test_provider_http_failure_classification(status, transient, calls, monkeypatch):
    import httpx
    seen = []
    def transport(request):
        seen.append(True)
        return httpx.Response(status, json={'secret': 'must never be included in an exception'})
    factory = httpx.Client
    monkeypatch.setattr(providers.httpx, 'Client', lambda **kwargs: factory(transport=httpx.MockTransport(transport), **kwargs))
    monkeypatch.setattr(providers.time, 'sleep', lambda _: None)
    with pytest.raises(ProviderError) as exc:
        providers.provider_json('https://example.com/test', 'private-key-test', {})
    assert isinstance(exc.value, ProviderUnavailable) is transient
    assert len(seen) == calls and 'secret' not in str(exc.value) and 'private-key' not in str(exc.value)


def test_invalid_provider_json_is_not_a_transient_fallback(monkeypatch):
    import httpx
    factory = httpx.Client
    monkeypatch.setattr(providers.httpx, 'Client', lambda **kwargs: factory(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text='not-json')), **kwargs))
    with pytest.raises(ProviderError) as exc:
        providers.provider_json('https://example.com/test', 'test-key', {})
    assert not isinstance(exc.value, ProviderUnavailable)


def test_near_zero_embedding_is_rejected(monkeypatch):
    monkeypatch.setattr(providers, 'provider_json', lambda *a, **k: {'data':[{'index':0,'embedding':[1e-300]*1536}]})
    with pytest.raises(ProviderError):
        providers.embed(['python'])


def test_release_version_is_consistent(monkeypatch):
    from fastapi.testclient import TestClient
    from rolecraft import __version__
    from rolecraft.operations import VERSION
    import app
    monkeypatch.delenv('DATABASE_URL', raising=False)
    assert VERSION == __version__ == app.app.version == '1.3.0'
    assert TestClient(app.app).get('/api/health').json()['version'] == __version__
