# Burhaniya Library Backend Patch

## Implemented

- Oversized-page segmentation during index construction. `b02` now rebuilds as 9 bounded segments instead of one 63,773-character record.
- Book-diversified search ranking, enabled by default, with `max_per_book` control.
- Relevance ordering using SQLite FTS5 `bm25` while retaining primary-source priority.
- True `total_hits` alongside `returned_count`.
- Multi-query exact search with `queries` and `operator: OR|AND`.
- New `get_passage(book_id, seq, query, context_chars)` MCP tool for bounded retrieval.
- Fully-vowelled Arabic query alignment fix, including superscript alif normalization.
- Expanded automated tests: total counts, diversity, OR search, vowelled excerpts, and bounded passages.

## Not yet implemented

- Canonical-work / edition metadata and automatic collapse of equivalent editions.
- Chapter, poem, bayt, speech, article, and date metadata. These require source-specific extraction rules and/or curated metadata.
- Semantic/vector search. Exact search remains deliberately separate and reliable.

## Validation

- Index rebuilt successfully: 44 books, 21 primary, 23 secondary.
- Automated test suite: 12/12 passing.
