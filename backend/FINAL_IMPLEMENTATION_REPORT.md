# Al Burhania Research Library MCP — Final implementation

Release: **2.2.0**  
Tool-contract version: **5.1**  
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
- Reinforced the semantic workflow in tool descriptions: `search_library` → `get_passage` → `get_page`.
- Added `scripts/production_mcp_regression.py`, which connects to the public endpoint, follows `tools/list` pagination, rejects duplicate/missing/unexpected tools, checks schemas and metadata, explicitly verifies `get_passage`, and smoke-invokes all five tools.

### Retrieval and citation integrity

- Added an explicit, bounded primary-authority ranking policy. Relevance remains decisive when the evidence-score gap is substantial.
- Exposed the evidence score separately from `rank_score`; ranking is no longer an unexplained reordering of the displayed evidence score.
- Preserved exact zero-score hits. Literal presence is determined by evidence rather than by forcing BM25 above zero.
- Made `surface_form`, `corpus_form`, `normalized_form`, and normalization relations explicit in exact/terms/lexeme evidence.
- Added a warning for Arabic `ى`/`ي` normalization: it supports recall but never replaces the source surface form for quotation or lexical claims.
- Documented that `auto` is citation-capable only after auditing `match_type`, `matched_terms`, and returned evidence.
- Made `expand_top` deterministic: it returns exactly the requested number of successful passages, or an explicit per-item retrieval error.

### Dīwān structure and source fidelity

- Restored the original written Arabic qaṣīda ordinals in source headings while retaining numeric `qasida_number` metadata.
- Added a full structural gate for exactly 95 qaṣīdas and 2,682 abyāt, with continuous bayt numbering and stable identifiers.
- Fixed a parser/indexer defect affecting three abyāt whose text begins with parentheses:
  - qaṣīda 67, bayt 17
  - qaṣīda 79, bayt 21
  - qaṣīda 88, bayt 19
- Rebuilt and validated the shipped database and FTS index. All 2,682 stable bayt identifiers now resolve.
- Added `scripts/migrate_diwan_v5.py` for upgrading an existing prebuilt database safely.

### Regression policy

- Replaced a misleading single pass-rate with three classes:
  - **Hard gates**: any failure blocks deployment.
  - **Retrieval-quality gates**: threshold/benchmark failures block deployment.
  - **Efficiency warnings**: reported separately and do not automatically block deployment.
- Kept exact historical BM25 decimals and score-spread values as diagnostics, not permanent correctness definitions.
- Added score-semantic, normalization, Dīwān identity, evidence, trap-query, paraphrase, expansion, ranking-policy, manifest, and schema regressions.
- The Docker build now runs the complete local deployment gate.

## Verification results

Command:

```bash
python scripts/run_regression_suite.py
```

Result:

| Gate class | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Hard gates | 86 | 0 | 1 |
| Retrieval-quality gates | 3 | 0 | 0 |
| Efficiency checks | 2 | 0 | 0 |

Total: **92 tests**, **0 failures**, `deployment_blocked: false`.

The single skip is the optional local semantic-vector metadata check because local semantic search is disabled and no semantic artifact is shipped. This does not affect the exact, terms, lexeme, or hybrid production paths tested here.

Additional checks:

- SQLite integrity: `ok`
- Books: 43
- Pages/FTS rows: 6,935 / 6,935
- Dīwān qaṣīdas/abyāt: 95 / 2,682
- Missing Dīwān stable IDs: 0
- Compact response savings in the included diagnostic fixture: 41.9%
- Ultra-compact response savings: 49.2%

## Deployment and live verification

1. Deploy this package normally. The Docker build will run the local gate.
2. Confirm `/health` reports server `2.2.0`, tool-contract `5.1`, tool count `5`, and the exact required names.
3. From a networked environment with the project dependencies installed, run:

   ```bash
   python scripts/production_mcp_regression.py https://burhaniya-library-backend.onrender.com/mcp/
   ```

4. If ChatGPT continues to show four tools after production passes, refresh or reconnect the connector and begin a new session so the host retrieves the new catalogue.

The live public MCP gate cannot be truthfully completed before this modified build is deployed. The supplied script is the final post-deployment acceptance test and should be added to CI/CD as MCP-000/MCP-001.

## Deliberately not activated

A token-table feature and a separate internal Dīwān-parallel index remain future research enhancements. They were not enabled with a naïve Arabic stem/root implementation because doing so would weaken the citation-integrity guarantees established by this release. Their activation should require independently validated linguistic fixtures and new hard gates.

## Primary protocol references

- [MCP tools specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
- [Official MCP Python SDK client guide](https://github.com/modelcontextprotocol/python-sdk/blob/v1.x/docs/client.md)
- [Official MCP Python SDK testing guide](https://github.com/modelcontextprotocol/python-sdk/blob/v1.x/docs/testing.md)
