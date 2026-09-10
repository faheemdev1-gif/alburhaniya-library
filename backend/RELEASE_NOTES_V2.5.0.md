# Al Burhaniya Library 2.5.0

This release implements the engineering actions from the 9 September 2026
live optimization audit without changing the five-tool MCP surface.

## Reliability

- Uses one SQLite read connection per worker thread instead of sharing one
  process-wide connection across concurrent requests.
- Retries transient SQLite busy/locked/interrupted failures with a bounded
  50 ms / 150 ms backoff.
- Returns concise structured errors containing `code`, `retryable`, and
  `request_id`; raw exception or HTML payloads are not returned to clients.
- Adds request correlation IDs and elapsed-time logging to HTTP responses.

Cloudflare challenge and rate-limit policy remains an edge configuration
responsibility. The application now fails safely when a request reaches it,
but it cannot modify a challenge generated before traffic reaches the app.

## Discovery and performance

- Hybrid candidates are batch-loaded rather than fetched page by page.
- The default locally scored hybrid pool is bounded at 250 pages and remains
  configurable through `HYBRID_CANDIDATE_POOL`.
- Multi-query `OR` alternatives remain alternatives during final local
  evidence scoring.
- Long questions that exhaust exact, terms, and hybrid search receive a
  deterministic fallback made only from adjacent source-surface topic phrases
  and content terms. Every result declares `match_type=reformulated`, the exact
  `reformulated_query`, and `reformulation_method`.

## Count semantics

The ambiguous `total_hits` headline has been removed from MCP search results.
When `include_counts=true`, responses now distinguish:

- `retrieval_hit_count`
- `retrieval_hit_count_relation` (`exact` or `lower_bound`)
- `retrieval_hit_count_scope`
- `literal_matching_pages`
- `literal_occurrences`
- `census_matching_pages`
- `census_occurrences`
- `count_basis`

This makes it explicit when broader retrieval returns evidence even though the
complete literal query phrase has zero occurrences.

## Context and Dīwān text

- `get_passage` now accepts `context_mode="paragraph"` and `max_chars`.
- Complete paragraphs are declared with `context_scope`,
  `complete_paragraph`, and `context_cap_applied`.
- Complete qaṣīda retrieval remains available through `qasida_number`.
- Structured bayt text strips glued page footers and decorative rules while
  raw page text and printed-page metadata remain unchanged.
- Qaṣīda 91 bayts 12 and 22 are covered by regressions.

## Contract and validation

- Server version: `2.5.0`
- Tool contract: `alburhaniya-tools-v6`
- Contract version: `7.0`
- Local suite: 134 tests; 133 executed successfully and one optional local
  semantic-vector test skipped when `semantic_embeddings.npy` is absent.
