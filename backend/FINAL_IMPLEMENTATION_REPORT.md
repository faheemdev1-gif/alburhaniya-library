# Al Burhania Research Library MCP — implementation report

Release: **2.4.0**  
Tool-contract version: **6.0**  
Contract identifier: **`alburhaniya-tools-v5`**

## Outcome

This release makes literal research and corpus census safe by default. It also
turns the model-facing schema, corpus totals, provenance policy, and dangerous
Arabic boundary cases into deployment-blocking contracts.

The public MCP surface remains exactly five tools:

1. `search_library`
2. `get_passage`
3. `get_page`
4. `get_book`
5. `list_books`

## Research-integrity changes

### Whole-word evidence and graded normalization

- `whole_word=true` is the default for exact, terms, and census operations.
- `سر` cannot match `اليسرى`, `الأسرار`, `الإسراء`, or other longer tokens.
- `لا` cannot match `لأ` or a substring inside `الأحمدية`.
- Literal normalization strips tashkīl and normalizes Unicode Kaf only. It
  deliberately preserves hamza, `ى/ي`, and `ة/ه` distinctions.
- Broad normalization remains available only for lexeme/hybrid discovery. A
  broad candidate is labelled and is never counted as literal evidence.
- Search highlighting, result evidence, and occurrence counting use the same
  boundary-safe matcher.

### Stable and explicit census semantics

- Counts no longer inherit their meaning from retrieval mode.
- `count_basis="phrase"` counts the requested phrase; `term_bag` counts the
  requested terms. Every census returns its basis and semantics.
- The same phrase census is identical whether retrieval uses exact or terms.
- Explicit end-footnotes are excluded from the authorial-body index and counts.
- `min_tier=2` restricts retrieval and counts to authority tiers 1–2.

### No silent zeroes

- `auto` tries semantic fusion when available, then deterministically falls
  back through exact, terms, and hybrid retrieval.
- Every zero response includes diagnostics: attempted modes, per-term page and
  occurrence counts, dropped stopwords, spelling suggestions, suggested mode,
  and an explicit warning that zero is not proof of corpus absence.

### Page and structural evidence

- `get_page.max_chars` now defaults to 20,000. The longest current page fits in
  full, and every response declares `full_chars` and `truncated`.
- Bidi-inverted Qurʾān brackets are repaired only in display output; stored
  source letters remain untouched.
- Pages expose conservative `content_types`: body, heading, quran, hadith, and
  footnote. Search hits expose their `evidence_type`.
- TOC classification/downranking, printed-page fidelity, universal citation
  labels, and qaṣīda heading IDs remain protected by hard gates.

## Provenance and manhaj support

Books now expose:

- `compiler`
- `authorship_mode`
- `attribution_confidence`
- `provenance_status`

Unknown data is explicitly null/unverified; it is never guessed.

- b20–b22 identify `عبد الحميد بابكر` from corpus evidence.
- b42's compiler remains unverified; the connector explicitly says not to
  assume Safwat without documentary evidence.
- b01 remains provisionally secondary/tier 4 until its transmission status is
  resolved editorially.
- b23–b25 remain unresolved rather than inheriting b20–b22 metadata.

## Full qaṣīda context and internal parallels

The immutable five-tool contract is preserved. `get_passage` now accepts:

- `qasida_number` to return the complete qaṣīda in one call;
- a canonical bayt `stable_id`;
- `include_parallels` for the existing internal-parallel candidate index.

All 8,428 parallel rows remain `unverified_candidate` and
`citation_safe=false`. Prosody fields (`bahr`, `qafiya`, `rawi`) are returned as
`not_curated`/null until verified data exists; the server does not invent them.

## Model-facing schema parity

- The server reports version 2.4.0, contract 6.0, the exact tool names, a
  canonical schema-capability map, and a SHA-256 `schema_digest`.
- Startup fails if the FastMCP registry is not exactly the five-tool contract.
- Production CI retrieves the public `tools/list` catalogue with pagination,
  validates parameter schemas/defaults and the digest, singles out
  `get_passage`, and smoke-invokes all five tools.
- If a third-party host caches an older schema, the live gate reports the
  mismatch. The server cannot forcibly clear an external host's cache; after a
  schema-changing deploy, reconnect that host if the gate shows stale data.

## Independent enforcement

The GitHub Actions workflow runs on relevant pushes and pull requests, weekly,
and manually. It:

- rebuilds SQLite from source;
- independently scans corpus totals, every stable ID, ordinal continuity,
  mid-book TOC labels, provenance, whole-word `سر`/`لا`, and footnote leakage;
- deliberately corrupts a temporary database to prove the audit fails;
- runs classified hard, retrieval-quality, and efficiency gates;
- uploads diagnostic artifacts;
- checks the deployed MCP contract after the independent corpus gate.

## Verification

`python scripts/run_regression_suite.py`:

| Gate class | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Hard gates | 121 | 0 | 1 |
| Retrieval-quality gates | 3 | 0 | 0 |
| Efficiency checks | 2 | 0 | 0 |

Total: **127 tests**, **0 failures**, `deployment_blocked: false`.

The optional local semantic-vector metadata test is skipped because no vector
artifact is shipped. Exact, terms, lexeme, hybrid, fallback, and semantic-safety
logic are tested independently.

Independent corpus audit:

- 43 catalogue books / 6,935 pages
- 42 default-search books / 6,885 pages after b38→b37 edition deduplication
- 95 qaṣīdas / 2,682 continuously numbered abyāt
- zero malformed or duplicate stable IDs
- 95 original written ordinals; digest
  `c354110999fb08d95a8d8d090fa63cc9eb47ddb62e4ea77e25b7261b66676a8d`
- zero suspicious mid-book TOC pages
- whole-word b13-p97 `سر` tokens: 1
- whole-word b14-p246 `لا` tokens: 1
- explicit b13-p97 footnote excluded from the index
- provenance audit: pass

## Deployment

1. Overlay the release at the repository root.
2. Do not commit `backend/library.db`; Docker rebuilds it from source.
3. Push the source and let Render deploy.
4. Manually run **Connector regression gates** once after deployment.
5. Confirm the live artifact reports server 2.4.0, contract 6.0, five tools,
   the expected `schema_digest`, and `corpus_contract.status: ok`.
6. If ChatGPT or another host still presents an older schema, reconnect that
   connector and start a new session, then rerun the live gate.

Branch protection is an account setting. Require
`independent-corpus-and-regression` on `main` using `BRANCH_PROTECTION.md`.
