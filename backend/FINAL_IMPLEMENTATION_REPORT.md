# Al Burhania Research Library MCP — Final implementation

Release: **2.3.7**  
Tool-contract version: **5.8**  
Contract identifier: **`alburhaniya-tools-v5`**

## Outcome

This release implements the consolidated connector, retrieval, structural-integrity, and regression recommendations. The server now treats the following exact set as an immutable public contract:

1. `search_library`
2. `get_passage`
3. `get_page`
4. `get_book`
5. `list_books`

Startup and health checks fail if a required tool is missing, an unexpected tool is registered, or a name is duplicated. Every tool also publishes contract metadata, and the server instructions tell clients to report incomplete discovery when fewer than five tools are visible.

## Implemented changes

### Tool discovery and deployment safety

- Added a single canonical five-tool manifest in `app/mcp_contract.py`.
- Added startup validation against the actual FastMCP registry—not just a constant or count.
- Added contract/version/tool details to `/health`.
- Added contract metadata to all five MCP tool definitions.
- Made MCP `initialize` report application version `2.3.7` instead of the SDK package version.
- Exposed the live connector and computed corpus contracts through
  `list_books`, and the connector contract through `get_book`, so MCP-only
  clients can verify the release, 43/6,935 corpus totals, 95/2,682 Dīwān
  totals, and zero malformed stable IDs without calling `/health`.
- Reinforced the semantic workflow in tool descriptions: `search_library` → `get_passage` → `get_page`.
- Added `scripts/production_mcp_regression.py`, which connects to the public endpoint, validates the live corpus/health contract, follows `tools/list` pagination, rejects duplicate/missing/unexpected tools, checks schemas, application version and metadata, explicitly verifies `get_passage`, and smoke-invokes all five tools.

### Retrieval and citation integrity

- Added an explicit, bounded primary-authority ranking policy. Relevance remains decisive when the evidence-score gap is substantial.
- Exposed the evidence score separately from `rank_score`; ranking is no longer an unexplained reordering of the displayed evidence score.
- Preserved exact zero-score hits. Literal presence is determined by evidence rather than by forcing BM25 above zero.
- Made `surface_form`, `corpus_form`, `normalized_form`, and normalization relations explicit in exact/terms/lexeme evidence.
- Added a warning for Arabic `ى`/`ي` normalization: it supports recall but never replaces the source surface form for quotation or lexical claims.
- Documented that `auto` is citation-capable only after auditing `match_type`, `matched_terms`, and returned evidence.
- Made `expand_top` deterministic: it returns exactly the requested number of successful passages, or an explicit per-item retrieval error.
- Guaranteed `matched_terms` for every hybrid hit, including results sourced from an exact candidate path.
- Restricted the ى/ي ambiguity warning to genuine ى/ي surface transformations; article and ة/ه normalization no longer receive a false warning.

### Dīwān structure and source fidelity

- Restored the original written Arabic qaṣīda ordinals in source headings while retaining numeric `qasida_number` metadata.
- Added a full structural gate for exactly 95 qaṣīdas and 2,682 abyāt, with continuous bayt numbering and stable identifiers.
- Fixed a parser/indexer defect affecting three abyāt whose text begins with parentheses:
  - qaṣīda 67, bayt 17
  - qaṣīda 79, bayt 21
  - qaṣīda 88, bayt 19
- Rebuilt and validated the shipped database and FTS index. All 2,682 stable bayt identifiers now resolve.
- Added `scripts/migrate_diwan_v5.py` for upgrading an existing prebuilt database safely.
- Added a live-computed corpus contract to `/health`; startup fails if the actual database no longer contains 43 books, 95 qaṣīdas, 2,682 continuous abyāt, canonical stable IDs, or the original written ordinal checksum.

### Research indexes

- Added a positional `tokens` table containing authoritative `surface_form`, `token_norm`, character and token positions, optional audited `lemma`/`root`, structural qaṣīda/bayt fields, and stable bayt identity.
- Root and lemma values are nullable. They are assigned only from the versioned curated family set `curated-arabic-roots-v1`; the system never presents a guessed root as linguistic fact.
- Added `diwan_parallel_candidates`, ranked by shared rare curated roots.
- Every parallel row is permanently marked `review_status: unverified_candidate` and `citation_safe: 0`. It is a discovery lead, not a scholarly finding.
- Added `scripts/migrate_research_indexes_v6.py` for an existing database. A full rebuild creates both indexes automatically.

### Regression policy

- Replaced a misleading single pass-rate with three classes:
  - **Hard gates**: any failure blocks deployment.
  - **Retrieval-quality gates**: threshold/benchmark failures block deployment.
  - **Efficiency warnings**: reported separately and do not automatically block deployment.
- Kept exact historical BM25 decimals and score-spread values as diagnostics, not permanent correctness definitions.
- Added score-semantic, normalization, Dīwān identity, evidence, trap-query, paraphrase, expansion, ranking-policy, manifest, and schema regressions.
- The Docker build now runs the complete local deployment gate.

### Contents-page classifier correction

- Removed the unsafe rule that treated two decorative dot-runs as proof of a
  table of contents. It had mislabeled 1,105 pages, including substantive
  b29 page 35.
- Implicit contents pages now require repeated dotted leaders followed by
  trailing destination page numbers, sufficient entry density, and a
  front/back-matter location.
- Contextual headings such as `فهرس الجزء` remain authoritative, while prose
  mentions of a work named `الفهرس` do not trigger classification.
- A full-corpus audit now leaves 67 genuine contents pages. New hard gates
  protect b29 page 35 and validate every implicit TOC structurally.
- Increased the internal hybrid candidate pool so restored body pages cannot
  crowd known relevant evidence out before local evidence scoring. Public
  thresholds and response limits are unchanged.

### Qaṣīda-scoped census correction

- `include_counts` now sends `qasida_number` through both the page-count and
  occurrence-count paths instead of counting the entire selected book.
- The permanent gate asserts: `الله` in b14 as a whole is 133 pages / 310
  occurrences; qaṣīda 32 is 1 / 1; qaṣīda 91 is 0 / 0.
- The production MCP regression now checks the 0/0 qaṣīda-91 case and fails
  deployment if whole-book counts leak into a filtered census again.
- Empty qaṣīda scopes no longer emit corpus-wide spelling suggestions, which
  previously suggested the already-correct query word despite a valid 0/0
  scoped result.

### Ultra-compact expansion integrity

- `expand_top` is no longer silently discarded by `ultra_compact` response
  serialization.
- Requested bounded passage objects are retained under the abbreviated key
  `ep`; ordinary compact responses continue to use `expanded_passage`.
- Local and production hard gates require exactly two `ep` objects when
  `expand_top=2`.

### Ultra-compact structural visibility and independent audit

- Ultra-compact hits now expose `block_type` under `blk`, allowing low-token
  clients to distinguish `body` from `toc` evidence. The pre-existing `bt`
  key remains `bayt_to`, so Dīwān verse ranges remain backward-compatible.
- Added an independent corpus audit that does not import the server's contract
  checker. It validates canonical and duplicate stable IDs, continuous bayt
  numbering, written ordinals and digest, corpus totals, and suspicious
  mid-book TOC classifications directly from the rebuilt SQLite corpus.
- Added GitHub Actions gates for every relevant push/pull request and a manual
  post-deployment MCP test. This makes `malformed_stable_ids: 0` independently
  reproducible rather than relying only on the server's self-report.

### Canonical-edition deduplication

- Confirmed that all 50 pages of `b38` are substantially contained in `b37`,
  including 33 exact normalized full-page matches.
- Kept both records in the 43-book catalogue, preserving edition-specific
  pagination and direct `book_ids=["b38"]` retrieval.
- Marked `b37` canonical and `b38` a `duplicate_excerpt`. Whole-library
  retrieval and occurrence counts now use 42 canonical/default-search books
  and 6,885 pages, preventing duplicated evidence and inflated censuses.
- Exposed the edition relationship through `list_books`, `get_book`, explicit
  compact results, ultra-compact `canon`/`er`, and the corpus contract.

### CI enforcement and diagnostics

- Corrected repository-root path filters to monitor `backend/**` on pushes and
  pull requests to `main`.
- Added a Monday 03:00 UTC schedule that runs the independent corpus gate and
  the live production contract in sequence.
- Updated official JavaScript actions to their Node 24-based v7 releases.
- Added 30-day downloadable audit, negative-control, regression, and live MCP
  artifacts.
- Added a safe negative control that corrupts only a temporary database copy
  and proves the independent audit reports the malformed ID and fails.
- Added branch-protection instructions; GitHub repository rules must require
  `independent-corpus-and-regression` because a workflow file cannot protect
  `main` by itself.

### GitHub-safe deployment packaging

- `library.db` is generated and ignored instead of committed. Its research indexes make it approximately 212 MB, above GitHub's 100 MB per-file limit.
- `.dockerignore` also excludes any local database copy so it is not uploaded as Docker build context before the reproducible build runs.
- Docker now runs `python scripts/build_index.py` from the authoritative source books before the regression gate.
- Added `GITHUB_PUSH_FIX.md` with a safe soft-reset procedure that removes the rejected database blob from unpushed local history without discarding working-tree changes.
- Git LFS is intentionally unnecessary for this reproducible build artifact.

## Verification results

Command:

```bash
python scripts/run_regression_suite.py
```

Result:

| Gate class | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Hard gates | 110 | 0 | 1 |
| Retrieval-quality gates | 3 | 0 | 0 |
| Efficiency checks | 2 | 0 | 0 |

Total: **116 tests**, **0 failures**, `deployment_blocked: false`.

The single skip is the optional local semantic-vector metadata check because local semantic search is disabled and no semantic artifact is shipped. This does not affect the exact, terms, lexeme, or hybrid production paths tested here.

Additional checks:

- SQLite integrity: `ok`
- Books: 43
- Pages/FTS rows: 6,935 / 6,935
- Dīwān qaṣīdas/abyāt: 95 / 2,682
- Missing Dīwān stable IDs: 0
- Indexed Arabic tokens: 1,726,697
- Curated/versioned rooted tokens: 45,861
- Unverified Dīwān parallel candidates: 8,428
- Compact response savings in the included diagnostic fixture: 41.9%
- Ultra-compact response savings: 49.2%

## Deployment and live verification

1. Deploy this package normally. The Docker build will run the local gate.
2. Confirm `/health` reports server `2.3.7`, tool-contract `5.8`, tool count `5`, and `corpus_contract.status: ok`.
3. From a networked environment with the project dependencies installed, run:

   ```bash
   python scripts/production_mcp_regression.py https://burhaniya-library-backend.onrender.com/mcp/
   ```

4. Reconnect the ChatGPT connector and begin a new session so the host retrieves the `2.3.7`/`5.8` catalogue and corrected descriptions.

The live public MCP gate cannot be truthfully completed before this modified build is deployed. The supplied script is the final post-deployment acceptance test and should be added to CI/CD as MCP-000/MCP-001.

## Citation boundary

The token and parallel indexes do not alter public search evidence. Surface text remains authoritative. Nullable curated roots assist discovery, and Dīwān parallels remain unverified candidates until reviewed against the original abyāt.

## Primary protocol references

- [MCP tools specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
- [Official MCP Python SDK client guide](https://github.com/modelcontextprotocol/python-sdk/blob/v1.x/docs/client.md)
- [Official MCP Python SDK testing guide](https://github.com/modelcontextprotocol/python-sdk/blob/v1.x/docs/testing.md)
