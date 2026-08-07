# Retrieval v3 implementation

This backend implements the requested low-token research workflow while
retaining the existing SQLite FTS5 index, Arabic normalization, source grades,
tiers, printed-page citations, and full-page fallback.

## MCP contract

- Every tool now declares structured output, so MCP clients receive native
  `structuredContent`. The MCP SDK may also emit a text fallback for older
  clients, but modern clients can consume the object directly.
- `search_library` accepts `query` or `queries`, `book_scope`, `source_code`,
  `match_mode`, `limit`, `context_chars`, and `include_counts`.
- `match_mode` is `exact`, `terms`, `hybrid`, or `lexeme`.
- `include_counts` defaults to `false`; count and occurrence scans are skipped.
- Search hits carry stable `match_id` values, relevance scores, and bounded
  excerpts.
- `get_passage(match_id, context_chars=600)` returns focused context.
- `get_page` remains available as the deliberate full-page fallback.

## Retrieval behavior

- `exact` preserves phrase-sensitive religious-text retrieval.
- `terms` requires all normalized terms even when they are separated.
- `hybrid` performs local reciprocal-rank fusion over exact-phrase, all-term,
  and any-term FTS/BM25 signals, then applies the existing source-tier priority.
  It is deterministic and needs no external service at request time.
- Multiple queries are searched and de-duplicated in one call.
- Arabic title fragments resolve internally to one book or a complete series;
  for example, `شرح شراب الوصل` resolves to b20–b25.

## Validation

The suite contains 24 passing tests covering compact payloads, normalization,
source filtering, multi-query retrieval, search modes, stable passage ids,
title scopes, optional counts, single-book pagination, and hybrid recovery.

Run:

```bash
python -m unittest discover -s tests -v
```
