# Optimization implementation - 13 August 2026

Applied from `burhaniya-library-optimization-report(1).pdf`.

## Implemented

- Unified five-tool MCP contract; batch IDs are accepted by `get_passage`.
- Higher-is-better relevance scores in every relevance-ranked match mode.
- Chunk-local hybrid scoring, Arabic stopword removal, and local match offsets.
- Shared canonical normalization/token/lexical-expansion pipeline.
- Explicit `surface_occurrences` and `normalized_occurrences`.
- Dīwān qasida/bayt parsing, structured citation fields, and qasida filtering.
- Weighted tier/relevance ranking instead of an absolute primary-tier gate in hybrid.
- `match_mode="auto"` cascade and explicit `match_type` on every result.
- Inline top-result expansion with `expand_top` / `expand_chars`.
- Default discovery context reduced to 60 characters.
- Legacy `standard` response mode removed from the MCP schema.

## Verification

- Rebuilt `library.db`: 43 books, 6,934 pages.
- 33 automated tests pass.
- Contract inspection confirms exactly five tools and all required parameters.
