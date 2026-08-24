# Al Burhania connector v2.3.4

Tool contract: **5.5** (`alburhaniya-tools-v5`)  
Required public tools: exactly **5**

## Qaṣīda-filtered counts

- Fixed `include_counts` so `qasida_number` applies to page totals,
  occurrence totals, and every `per_query` statistic.
- Verified fixed invariants for `الله` in b14:
  - whole book: 133 matching pages / 310 occurrences;
  - qaṣīda 32: 1 matching page / 1 occurrence;
  - qaṣīda 91: 0 matching pages / 0 occurrences.
- Retrieval already respected the qaṣīda filter; this release makes census
  metadata use the identical scope.

## MCP-visible verification evidence

- `list_books` now exposes `connector_contract` and the live-computed
  `corpus_contract` alongside the 43-book catalogue.
- `get_book` exposes `connector_contract` for direct version verification.
- MCP-only clients can now verify server 2.3.4, contract 5.5, the exact
  five-tool manifest, 6,935 pages, 95 qaṣīdas, 2,682 bayts, continuous bayt
  numbering, original written ordinals, and zero malformed stable IDs.
- This adds no tool: the immutable public surface remains exactly five tools.

## Claude feedback disposition

- The TOC corpus sweep is already permanent: every implicit TOC must have
  structural trailing-page entries and occur in front/back matter. The known
  b29 page 35 false positive remains a hard negative control.
- A blanket “last 5% only” assertion was not adopted because genuine front
  indexes (b29 pages 2–5) and an explicit internal volume index (b13 page 174)
  would be incorrectly rejected.
- Version, corpus totals, and malformed-ID evidence are now visible through
  MCP as well as `/health`.

## Verification

- Regression result: **112 tests, 0 failures**; 1 optional semantic-vector
  test skipped because semantic vectors are intentionally not bundled.
- Gate totals: 106 hard, 3 retrieval-quality, and 2 efficiency checks passed;
  `deployment_blocked: false`.
