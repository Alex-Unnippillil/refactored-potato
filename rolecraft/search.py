from __future__ import annotations

import os
import time

from .models import SearchRequest
from .providers import ProviderError, rerank
from .store import get_store
from .text import LABELS, evidence, themes


def fuse(lexical: list[tuple[str, float]], semantic: list[tuple[str, float]], semantic_weight: float = 0.65) -> dict[str, float]:
    """Weighted reciprocal-rank fusion; scores from unlike retrievers aren't mixed."""
    scores: dict[str, float] = {}
    for ranking, weight in ((lexical, 1 - semantic_weight), (semantic, semantic_weight)):
        if weight == 0:
            continue
        for rank, (identifier, _) in enumerate(ranking, start=1):
            scores[identifier] = scores.get(identifier, 0.0) + weight / (60 + rank)
    return scores


def search(request: SearchRequest, store=None) -> dict:
    store = store or get_store()
    start = time.perf_counter()
    search_text = ' '.join([request.query, *(LABELS[p] for p in request.preferences)]).strip()
    raw = store.retrieve(search_text, request.filters, semantic=request.semantic_weight > 0)
    retrieval_ms = round((time.perf_counter() - start) * 1000, 1)
    scores = fuse(raw['lexical'], raw['semantic'], request.semantic_weight)
    lexical_scores, semantic_scores = dict(raw['lexical']), dict(raw['semantic'])
    pool = [job for job in raw['jobs'] if not search_text or job['id'] in scores]
    wanted = set(request.preferences) | (themes(request.query) & set(LABELS))
    # Copy payloads so the immutable corpus is not polluted by request metadata.
    results = []
    for payload in pool:
        job = dict(payload)
        coverage = len(wanted & themes(job['description'])) / max(1, len(wanted))
        job['evidence'] = evidence(job['description'], request.query, request.preferences)
        job['unconfirmed_preferences'] = [LABELS[p] for p in request.preferences if p not in themes(job['description'])]
        job['scores'] = {'lexical': round(lexical_scores.get(job['id'], 0), 5), 'semantic': round(semantic_scores.get(job['id'], 0), 5), 'rrf': round(scores.get(job['id'], 0), 7)}
        job['_rank'] = scores.get(job['id'], 0) + (coverage * 0.003 if search_text else 0)
        job['fit'] = 'Explore this role' if not search_text else ('Strong signals' if coverage >= 0.66 and wanted else 'Relevant match')
        results.append(job)
    results.sort(key=lambda job: (-job['_rank'], job['id']))
    warnings = []
    reranker = 'Evidence-aware local reranker'
    # Optional cross-encoder is called only for live, authenticated searches.
    if store.mode == 'live' and search_text and os.getenv('COHERE_API_KEY'):
        candidates = results[:40]
        try:
            order = rerank(search_text, [f"{j['title']} at {j['company']}\n{j['description']}" for j in candidates])
            if order is not None:
                results = [candidates[i] for i in order] + results[len(candidates):]
                reranker = 'Cohere cross-encoder (top 40)'
        except ProviderError:
            warnings.append('The optional cross-encoder is unavailable; evidence-aware ranking was used.')
    for job in results:
        del job['_rank']
    total = len(results)
    offset = (request.page - 1) * request.page_size
    elapsed = round((time.perf_counter() - start) * 1000, 1)
    return {
        'jobs': results[offset:offset + request.page_size], 'total': total,
        'eligible_count': raw['eligible_count'], 'page': request.page, 'page_size': request.page_size,
        'has_more': offset + request.page_size < total, 'mode': store.mode,
        'query': request.query, 'filters': request.filters.model_dump(), 'preferences': request.preferences,
        'warnings': warnings,
        'trace': {
            'engine': 'SQLite FTS5 + local concept vectors' if store.mode == 'demo' else 'PostgreSQL FTS + pgvector',
            'embedding': '256-dimensional demo concept index; not a neural model' if store.mode == 'demo' else 'text-embedding-3-small · 1536 dimensions',
            'retrieval_ms': retrieval_ms, 'total_ms': elapsed,
            'lexical_candidates': len(raw['lexical']), 'semantic_candidates': len(raw['semantic']),
            'fused_candidates': total, 'reranker': reranker, 'rrf_k': 60,
            'semantic_weight': request.semantic_weight,
            'constraint_policy': 'AND filters run before both retrieval branches. Unknown salary is excluded when a minimum is set.',
            'candidate_cap': 100, 'truncated': raw['eligible_count'] > 100,
        },
    }
