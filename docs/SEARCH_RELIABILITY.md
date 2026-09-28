# Search reliability and source evidence — 1.3

Rolecraft separates **enforceable structured constraints**, **retrieval relevance**, and **what a job listing actually says**. Source text is not independent evidence of a workplace's real conditions. No matching percentage is presented as hiring probability.

## Selected-preference evidence

Every search result now includes `preference_assessments`, one entry per explicitly selected preference. Free-text terms influence retrieval but do not silently become selected preferences. The versioned policy is `selected-preferences-lexical-v1`.

| API status | Interface label | Meaning |
|---|---|---|
| `supporting` | Supporting text | These rules found affirmative source wording. This is a claim by the source, not a verified benefit. |
| `conflicting` | Conflicting text | An explicit conflicting phrase or a nearby denial was found. |
| `mixed` | Mixed evidence | Both supporting and conflicting source wording were found. |
| `uncertain` | Uncertain wording | The wording is planned, hedged, not guaranteed, or otherwise ambiguous to the rules. |
| `not_found` | Not stated | No explicit wording was recognized. The benefit may still exist. |

The English rules use clause boundaries, contrast markers, bounded nearby negation, and a small vocabulary of explicit support/conflict phrases. For example, “We provide mentorship” supports mentorship, “No mentorship is offered” conflicts, and “We may offer mentorship later” is uncertain. Merely hiring junior engineers does not prove mentorship; high company growth does not prove a learning budget.

These are transparent lexical heuristics, **not a language-understanding model**. They can misread attribution, complex or distant negation, indirect language, sarcasm, multilingual descriptions and team-specific exceptions. `supporting` can coexist with an uncertain excerpt without establishing a guarantee. Read the complete description and confirm benefits with the employer. Unknown eligibility or compensation is never inferred from these cues.

Each excerpt includes `quote`, `start`, `end`, and `polarity`. Offsets are **Unicode code-point offsets** into the normalized `description` returned with that result, not byte offsets, JavaScript UTF-16 indices or offsets into the upstream HTML. The invariant is Python `description[start:end] == quote`. Excerpts are bounded to 500 characters. At most one excerpt per polarity per preference is retained; the compact result evidence favors conflicting wording so an excerpt cap cannot hide it behind affirmative cues. The audit exposes all retained preference excerpts.

### Ranking and explanations

SQL constraints remain mandatory before both retrieval branches. Weighted reciprocal-rank fusion uses `k=60`. Repeated occurrences of an ID within a branch do not accumulate extra RRF contributions. Before an optional Cohere re-rank, the local preference adjustment is:

```text
0.003 × (supporting preference count − conflicting/mixed preference count)
        / max(1, selected preference count)
```

A mixed or conflicting preference is never counted as supporting. Neutral and uncertain states get no positive adjustment. All of these are ranking cues, not hard filters. An optional cross-encoder can change the final order of the top 40 candidates.

`retrieval_explanation` exposes keyword/semantic candidate ranks, effective semantic weight, the local adjustment, support/conflict counts and policy version. Missing branch ranks mean that the job was not retrieved by that branch. Raw scores from different branches are not comparable probabilities. The job detail includes the source audit, ranks, full description and original source link; briefs carry preference caveats and retrieval warnings.

## Explicit hybrid fallback

`SearchRequest.allow_keyword_fallback` defaults to `true` for compatibility. Only a hybrid request (`0 < semantic_weight < 1`) may recover from `ProviderUnavailable` by rerunning **the identical query and filters** with semantic retrieval disabled. A single request still consumes one search budget, even if it needs this recovery. The fallback does not retrieve fictional data or broaden location, pay, currency, work-style or experience constraints.

| Failure or request | Behavior |
|---|---|
| Transport error or upstream HTTP 429, 500, 502, 503, 504 during query embedding | Hybrid search can use keyword retrieval with a persistent notice. Existing bounded retries still apply. |
| Explicit meaning-only mode (`semantic_weight=1`) | Fails; it never substitutes keyword results. |
| `allow_keyword_fallback=false` | Fails; useful for strict evaluation and clients requiring semantic retrieval. |
| Missing/wrong credentials, model/index mismatch, incompatible vectors, malformed provider JSON | Fails; configuration or schema failures are not hidden as transient outages. |
| PostgreSQL, access-control or request-validation failure | Fails; these are never converted to successful degraded search. |
| Explicit keyword mode (`semantic_weight=0`) or unfiltered browse | Does not request query embeddings. |

A fallback response has `retrieval_status: "keyword_fallback"`, a warning, `trace.degraded: true`, effective `trace.semantic_weight: 0`, and the original `trace.requested_semantic_weight`. The UI shows **Keywords only · fallback** and a persistent explanation; the evidence brief carries that warning too. A later successful search or explicit keyword request clears the old notice. A failed request clears old traces and results instead of implying the old retrieval succeeded. Every new hybrid request attempts semantic retrieval again: there is no sticky hidden fallback or process-local circuit breaker.

Keyword search is not equivalent to semantic retrieval. It may produce fewer or no results, especially for long free-text queries with several preference terms. The notice does not promise equivalent relevance. A 429 may reflect exhausted quota rather than a short outage: inspect the provider before repeatedly retrying.

The optional Cohere failure path remains independent: if the re-ranker fails, already retrieved candidates retain local evidence-aware ordering with a warning. It does not alter the retrieval branch labels. Provider credentials and response bodies are not returned to the client. Embedding responses require a complete integer-index permutation, exactly 1,536 finite bounded numeric values per vector, and a non-negligible vector norm. Booleans and coercible index strings/floats are rejected. Re-ranker indices must also be an exact integer permutation.

## Consistent reads during source refreshes

Query embeddings are obtained **before** opening the SQL read transaction. Eligible counts, full-text retrieval, exact vector retrieval and returned job payloads execute in one PostgreSQL **repeatable-read, read-only** transaction. A concurrently committed source refresh cannot swap the payload halfway through that request. A later request sees the new committed data. This is per-request consistency, not a persistent snapshot across separate pagination requests.

Saved-role lookup and export now use the same active/fresh/non-expired predicates as search. A saved ID may remain in browser storage after a role becomes unavailable, but stale or expired live role data is not re-served just because its ID was saved. The configured `SOURCE_FRESH_DAYS` rule applies. Demo data stays immutable and explicitly fictional.

## Locking the private workspace

After access is supplied, **Lock workspace** clears the page's access token, result payload cache, detail/brief content, comparison state, source drafts, search trace, query and displayed results. It aborts client requests and advances an access epoch. Responses started under the old epoch cannot repopulate a locked screen, generate an export or contaminate a replacement token's results—even when the HTTP response has already arrived but parsing/UI processing is delayed.

This is a **local page lock**, not server-side token revocation, multi-tenant identity or device encryption. Rotate a compromised token in the deployment secret manager. Previously saved role IDs and explicitly saved search presets remain in this browser's local storage; erase site data to remove them. Locking does not cancel an import already admitted by the server or undo a request/provider charge. Cancel a queued import through operations separately. No access/provider token is intentionally stored in local/session storage or a URL.

## Verification and release acceptance

No schema migration is introduced in 1.3. Existing live workspaces still require migrations 001–003; keep `python scripts/manage.py migrate` in the normal upgrade procedure. Web and operations endpoints share the same version constant.

CI includes source-evidence polarity and exact-span cases, malformed-provider contracts, strict/fallback cases, and a real PostgreSQL test that commits a competing update between retrieval and payload reading. Browser tests exercise desktop/mobile audits, a synthetic provider outage over the real HTTP/API/PostgreSQL stack, explicit meaning-only failure, keyword recovery, token replacement and late search/saved/export/brief responses. Provider calls are controlled fixtures; **these tests do not prove real provider availability, billing, credentials or relevance quality**. A deliberate delayed real response tests client race protection without substituting API data.

The README screenshots use only the running unauthenticated fictional demo, not private source data or a fake hosted service. Capture provenance includes the application-source SHA-256 fingerprint. Real live credentials and deployment must be accepted separately:

1. Confirm the deployed Git commit, `/api/health` version, authenticated `/api/readiness`, and corpus freshness.
2. Run a real authorized hybrid search with explicit hard filters, inspect the effective strategy, source excerpts and original listing.
3. Exercise a controlled provider outage in staging; verify the fallback notice, unchanged filters and meaning-only refusal.
4. Lock during a request and verify no private result or download appears afterward. Verify scheduled imports continue to respect their independent cancellation/authorization boundaries.

The authored eight-query fictional-corpus evaluator remains a regression diagnostic, not a held-out benchmark. This release does not add multi-user accounts, employer verification, public-service abuse protection or managed production hosting.

## Primary technical references

- [PostgreSQL SET TRANSACTION](https://www.postgresql.org/docs/16/sql-set-transaction.html): repeatable-read and read-only transaction semantics.
- [OpenAI embeddings](https://developers.openai.com/api/docs/guides/embeddings): embedding response contract and model dimensions.
- [Cohere v2 rerank](https://docs.cohere.com/v2/reference/rerank): returned document indices and re-ranking API.
