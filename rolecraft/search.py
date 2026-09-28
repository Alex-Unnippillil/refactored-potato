from __future__ import annotations

import os
import time

from .models import SearchRequest
from .providers import ProviderError, ProviderUnavailable, rerank
from .store import get_store
from .text import LABELS
from .signals import POLICY, assess_preferences, excerpts


def fuse(lexical: list[tuple[str, float]], semantic: list[tuple[str, float]], semantic_weight: float = 0.65) -> dict[str, float]:
    """Weighted reciprocal-rank fusion; scores from unlike retrievers aren't mixed."""
    scores: dict[str, float] = {}
    for ranking, weight in ((lexical, 1 - semantic_weight), (semantic, semantic_weight)):
        if weight == 0:
            continue
        seen = set()
        for rank, (identifier, _) in enumerate(ranking, start=1):
            if identifier in seen:
                continue
            seen.add(identifier)
            scores[identifier] = scores.get(identifier, 0.0) + weight / (60 + rank)
    return scores


def search(request: SearchRequest, store=None) -> dict:
    store = store or get_store()
    start = time.perf_counter()
    search_text = ' '.join([request.query, *(LABELS[p] for p in request.preferences)]).strip()
    warnings = []
    effective_weight = request.semantic_weight
    degraded = False
    try:
        raw = store.retrieve(search_text, request.filters, semantic=effective_weight > 0)
    except ProviderUnavailable:
        # Never degrade an explicit meaning-only search or a strict API request.
        # Configuration, schema, database and authorization failures propagate.
        if not (0 < effective_weight < 1 and request.allow_keyword_fallback):
            raise
        raw = store.retrieve(search_text, request.filters, semantic=False)
        effective_weight = 0
        degraded = True
        warnings.append('Semantic search is temporarily unavailable. Showing keyword-only results with all hard filters unchanged. Retry to restore hybrid retrieval.')
    retrieval_ms = round((time.perf_counter() - start) * 1000, 1)
    scores = fuse(raw['lexical'], raw['semantic'], effective_weight)
    lexical_scores, semantic_scores = dict(raw['lexical']), dict(raw['semantic'])
    pool = [job for job in raw['jobs'] if not search_text or job['id'] in scores]
    lexical_ranks = {identifier: rank for rank, (identifier, _) in enumerate(raw['lexical'], 1)}
    semantic_ranks = {identifier: rank for rank, (identifier, _) in enumerate(raw['semantic'], 1)}
    # Copy payloads so the immutable corpus is not polluted by request metadata.
    results = []
    for payload in pool:
        job = dict(payload)
        assessments = assess_preferences(job['description'], request.preferences)
        supporting = sum(a['status'] == 'supporting' for a in assessments)
        conflicting = sum(a['status'] in ('conflicting', 'mixed') for a in assessments)
        coverage = supporting / max(1, len(assessments))
        adjustment = (supporting - conflicting) / max(1, len(assessments)) * 0.003 if search_text else 0
        job['preference_assessments'] = assessments
        job['evidence'] = excerpts(job['description'], request.query, assessments)
        job['unconfirmed_preferences'] = [a['label'] for a in assessments if a['status'] != 'supporting']
        job['scores'] = {'lexical': round(lexical_scores.get(job['id'], 0), 5), 'semantic': round(semantic_scores.get(job['id'], 0), 5), 'rrf': round(scores.get(job['id'], 0), 7)}
        job['retrieval_explanation'] = {
            'keyword_rank': lexical_ranks.get(job['id']), 'semantic_rank': semantic_ranks.get(job['id']),
            'effective_semantic_weight': effective_weight, 'preference_adjustment': round(adjustment, 7),
            'supporting_preferences': supporting, 'conflicting_preferences': conflicting,
            'evidence_policy': POLICY,
        }
        job['_rank'] = scores.get(job['id'], 0) + adjustment
        job['fit'] = ('Conflicting preference text' if conflicting else
                      'Supporting preference text' if supporting and coverage == 1 else
                      'Some supporting text' if supporting else
                      'Preferences unconfirmed' if assessments else
                      'Relevant match' if search_text else 'Explore this role')
        results.append(job)
    results.sort(key=lambda job: (-job['_rank'], job['id']))
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
    strategy = 'browse' if not search_text else 'keyword_fallback' if degraded else 'keywords' if effective_weight == 0 else 'semantic' if effective_weight == 1 else 'hybrid'
    return {
        'jobs': results[offset:offset + request.page_size], 'total': total,
        'eligible_count': raw['eligible_count'], 'page': request.page, 'page_size': request.page_size,
        'has_more': offset + request.page_size < total, 'mode': store.mode,
        'query': request.query, 'filters': request.filters.model_dump(), 'preferences': request.preferences,
        'warnings': warnings, 'retrieval_status': strategy,
        'trace': {
            'engine': 'SQLite FTS5 + local concept vectors' if store.mode == 'demo' else 'PostgreSQL FTS + pgvector',
            'embedding': 'Not used for this request' if not search_text or effective_weight == 0 else '256-dimensional demo concept index; not a neural model' if store.mode == 'demo' else 'text-embedding-3-small · 1536 dimensions',
            'retrieval_ms': retrieval_ms, 'total_ms': elapsed,
            'lexical_candidates': len(raw['lexical']), 'semantic_candidates': len(raw['semantic']),
            'fused_candidates': total, 'reranker': reranker, 'rrf_k': 60,
            'semantic_weight': effective_weight, 'requested_semantic_weight': request.semantic_weight,
            'retrieval_status': strategy, 'degraded': degraded, 'evidence_policy': POLICY,
            'snapshot_policy': 'Repeatable-read, read-only per request' if store.mode == 'live' else 'Immutable demo corpus',
            'preference_policy': 'Only selected preferences are assessed; lexical source cues are not independent verification.',
            'constraint_policy': 'AND filters run before both retrieval branches. Unknown salary is excluded when a minimum is set.',
            'candidate_cap': 100, 'truncated': raw['eligible_count'] > 100,
        },
    }
