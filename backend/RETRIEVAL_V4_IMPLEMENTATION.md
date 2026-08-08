# Retrieval V4 implementation

Implemented on 2026-08-08:

- Exact phrase queries expand Arabic definite-article variants at query time.
- Terms and hybrid modes remove a conservative Arabic stopword set.
- Hybrid retrieval reranks page candidates using co-occurrence inside overlapping
  700-character windows, without rebuilding the shipped index.
- Hybrid scores are normalized to 0–1 and support `min_score`.
- `get_passage` accepts an optional `query` to restore `<mark>` highlighting.
- `get_passages` batches up to 20 match IDs per request.
- Passage responses omit null fields, the redundant source code, and match-ID echoes.

The shipped database has no `chunks` or `chunks_fts` table. The `c` component in
existing match IDs is a character offset, not a chunk identifier. Chunk-local
scoring is therefore performed over page candidates at request time.

External keep-alive scheduling and citation-label enrichment are deployment/data
operations and are not embedded in this backend patch.
