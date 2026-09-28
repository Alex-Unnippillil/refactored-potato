"""Distinguish recoverable transport outages from invalid provider contracts."""

import httpx
import pytest

from rolecraft import providers
from rolecraft.models import SearchRequest
from rolecraft.search import search


@pytest.fixture
def install_transport(monkeypatch):
    """Keep HTTPX's request/response handling real; replace network I/O only."""
    factory = httpx.Client
    monkeypatch.setattr(providers.time, 'sleep', lambda _: None)
    monkeypatch.delenv('COHERE_API_KEY', raising=False)

    def install(handler):
        monkeypatch.setattr(providers.httpx, 'Client', lambda **kwargs: factory(
            transport=httpx.MockTransport(handler), **kwargs))

    return install


@pytest.mark.parametrize('failure', [
    httpx.LocalProtocolError, httpx.UnsupportedProtocol, httpx.DecodingError,
    httpx.TooManyRedirects, httpx.InvalidURL,
])
def test_invalid_request_or_response_contract_is_not_retried_or_degraded(failure, install_transport):
    attempts = []

    def fail(request):
        attempts.append(request)
        raise failure('sensitive provider details must not escape')

    install_transport(fail)
    with pytest.raises(providers.ProviderError) as caught:
        providers.provider_json('https://example.com/provider', 'private-test-key', {})
    assert not isinstance(caught.value, providers.ProviderUnavailable)
    assert len(attempts) == 1
    assert 'sensitive' not in str(caught.value)
    assert 'private-test-key' not in str(caught.value)


@pytest.mark.parametrize('failure', [
    httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout,
    httpx.ConnectError, httpx.ReadError, httpx.WriteError, httpx.RemoteProtocolError,
])
def test_recoverable_transport_failure_keeps_bounded_retry(failure, install_transport):
    attempts = []

    def fail(request):
        attempts.append(request)
        raise failure('sensitive network details')

    install_transport(fail)
    with pytest.raises(providers.ProviderUnavailable) as caught:
        providers.provider_json('https://example.com/provider', 'private-test-key', {})
    assert len(attempts) == 2
    assert 'sensitive' not in str(caught.value)


def test_retry_can_recover_a_network_interruption(install_transport):
    attempts = []

    def respond(request):
        attempts.append(request)
        if len(attempts) == 1:
            raise httpx.ReadError('temporary interruption')
        return httpx.Response(200, json={'ok': True})

    install_transport(respond)
    assert providers.provider_json('https://example.com/provider', 'test-key', {}) == {'ok': True}
    assert len(attempts) == 2


def test_malformed_compressed_response_is_not_treated_as_an_outage(install_transport):
    attempts = []

    def respond(request):
        attempts.append(request)
        return httpx.Response(200, headers={'Content-Encoding': 'gzip'},
                              content=b'this is not a gzip stream')

    install_transport(respond)
    with pytest.raises(providers.ProviderError) as caught:
        providers.provider_json('https://example.com/provider', 'test-key', {})
    assert not isinstance(caught.value, providers.ProviderUnavailable)
    assert len(attempts) == 1


def test_hybrid_search_does_not_hide_a_client_protocol_failure(install_transport):
    def fail(request):
        raise httpx.LocalProtocolError('invalid local request headers')

    install_transport(fail)

    class ProtocolFailureStore:
        mode = 'live'

        def __init__(self):
            self.calls = []

        def retrieve(self, query, filters, semantic=True):
            self.calls.append(semantic)
            if semantic:
                providers.provider_json('https://example.com/provider', 'test-key', {})
            return {'jobs': [], 'lexical': [], 'semantic': [], 'eligible_count': 0}

    store = ProtocolFailureStore()
    with pytest.raises(providers.ProviderError) as caught:
        search(SearchRequest(query='Python'), store)
    assert not isinstance(caught.value, providers.ProviderUnavailable)
    assert store.calls == [True]
