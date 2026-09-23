from __future__ import annotations

import json
import math
import os
import time
from typing import Any

import httpx

EMBEDDING_DIMENSIONS = 1536
EMBEDDING_MODEL = 'text-embedding-3-small'


class ProviderError(RuntimeError):
    """Safe, public failure message; provider bodies and secrets are never logged."""


def provider_json(url: str, key: str, payload: dict, timeout: float = 18) -> Any:
    if not key:
        raise ProviderError('The required provider is not configured.')
    for attempt in range(2):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
                with client.stream('POST', url, headers={'Authorization': f'Bearer {key}'}, json=payload) as response:
                    if response.status_code in (429, 502, 503, 504) and attempt == 0:
                        time.sleep(0.4)
                        continue
                    if not response.is_success:
                        raise ProviderError('An upstream provider is unavailable. Please try again later.')
                    body = bytearray()
                    for part in response.iter_bytes():
                        body.extend(part)
                        if len(body) > 8_000_000:
                            raise ProviderError('The provider response exceeded the safety limit.')
                    return json.loads(body)
        except (httpx.HTTPError, ValueError) as exc:
            if attempt == 0:
                continue
            raise ProviderError('An upstream provider could not be reached.') from exc
    raise ProviderError('An upstream provider is temporarily unavailable.')


def embed(texts: list[str]) -> list[list[float]]:
    model = os.getenv('OPENAI_EMBEDDING_MODEL') or EMBEDDING_MODEL
    if model != EMBEDDING_MODEL:
        raise ProviderError('The configured embedding model does not match this index. Re-index before changing models.')
    if not texts:
        return []
    if len(texts) > 64 or any(len(text) > 2500 for text in texts):
        raise ValueError('Embedding batch exceeds the ingestion budget.')
    raw = provider_json('https://api.openai.com/v1/embeddings', os.getenv('OPENAI_API_KEY', ''), {
        'model': model, 'input': texts, 'dimensions': EMBEDDING_DIMENSIONS,
    })
    try:
        data = sorted(raw['data'], key=lambda x: x['index'])
        if [x['index'] for x in data] != list(range(len(texts))):
            raise ValueError('Unexpected embedding indices.')
        vectors = [item['embedding'] for item in data]
        if any(len(v) != EMBEDDING_DIMENSIONS or not all(isinstance(n, (int, float)) and math.isfinite(n) for n in v) for v in vectors):
            raise ValueError('Invalid embedding contract.')
        return vectors
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderError('The embedding provider returned an incompatible response.') from exc


def rerank(query: str, documents: list[str]) -> list[int] | None:
    key = os.getenv('COHERE_API_KEY', '')
    if not key or not documents:
        return None
    raw = provider_json('https://api.cohere.com/v2/rerank', key, {
        'model': os.getenv('COHERE_RERANK_MODEL') or 'rerank-v3.5',
        'query': query, 'documents': documents, 'top_n': len(documents), 'max_tokens_per_doc': 2048,
    })
    try:
        indices = [int(item['index']) for item in raw['results']]
        if sorted(indices) != list(range(len(documents))):
            raise ValueError('Unexpected reranker indices.')
        return indices
    except (KeyError, ValueError, TypeError) as exc:
        raise ProviderError('The reranking provider returned an incompatible response.') from exc
