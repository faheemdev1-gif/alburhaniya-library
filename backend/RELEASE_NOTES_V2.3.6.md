# Al Burhania connector v2.3.6

Tool contract: **5.7** (`alburhaniya-tools-v5`)  
Required public tools: exactly **5**

## Ultra-compact structural classification

- Every ultra-compact search hit now exposes `block_type` under `blk` with
  the value `body` or `toc`.
- `bt` remains the existing abbreviation for `bayt_to`; it was deliberately
  not reused for block type, preventing a schema collision on Dīwān results.
- Local and live production gates verify both a known body page and a known
  contents page in ultra-compact mode.

## Independent CI integrity audit

- Added `scripts/independent_corpus_audit.py`, which does not import the
  server's corpus-contract code. It independently verifies all 2,682 canonical
  bayt IDs, duplicates, continuous numbering, 95 written ordinals, the ordinal
  digest, 43/6,935 corpus totals, and suspicious mid-book TOC labels.
- Added a GitHub Actions workflow that rebuilds `library.db` from authoritative
  source texts, runs the independent audit, and runs the classified regression
  suite on every relevant push and pull request.
- The workflow also provides a manual post-deployment job for MCP discovery,
  schemas, all five smoke calls, corpus metadata, `ep`, and `blk` checks.

## Verification

- Independent audit: **pass** — 43 books, 6,935 pages, 95 qaṣīdas,
  2,682 bayts, continuous numbering, 0 malformed IDs, 0 duplicate IDs,
  95 written ordinals, matching digest, and 0 suspicious mid-book TOC pages.
- Regression result: **114 tests, 0 failures**; one optional semantic-vector
  test skipped because semantic vectors are intentionally not bundled.
- Gate totals: 108 hard, 3 retrieval-quality, and 2 efficiency checks passed;
  `deployment_blocked: false`.
