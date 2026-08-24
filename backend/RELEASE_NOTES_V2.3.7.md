# Al Burhania connector v2.3.7

Tool contract: **5.8** (`alburhaniya-tools-v5`)  
Required public tools: exactly **5**

## Canonical-edition policy

- `b37` is the canonical `مسامرة الأبرار` record.
- `b38` remains in the catalogue as a separately paginated
  `duplicate_excerpt`, mapped to `canonical_book_id: b37`.
- Whole-library search and occurrence counts exclude `b38` by default.
- Explicit `book_ids: ["b38"]` and exact-title scope searches still return the
  edition with its own printed-page citations.
- The 43-book/6,935-page catalogue is unchanged; default canonical search uses
  42 books/6,885 pages.
- Compact explicit-edition hits expose full canonical metadata; ultra-compact
  hits use `canon` and `er`.

## Stronger automation

- Corrected push/PR path filters for the repository-root workflow.
- Push and pull-request checks target `main` automatically.
- A weekly Monday 03:00 UTC run performs the independent corpus audit first,
  followed by the live production MCP contract.
- Official actions now use Node 24-based v7 releases.
- Both jobs upload 30-day diagnostic artifacts.
- A negative control corrupts a temporary database copy and requires the audit
  to identify and reject the malformed stable ID.
- Added `BRANCH_PROTECTION.md` for making the corpus gate a required `main`
  status check.

## Verification

- Rebuilt corpus: 43 books / 6,935 pages.
- Canonical default search: 42 books / 6,885 pages.
- Independent audit: pass; b38→b37 alias verified with 33 exact normalized
  page matches.
- Negative control: pass; deliberately malformed ID detected and rejected.
- Regression suite: **116 tests, 0 failures**, one optional semantic-vector
  test skipped; 110 hard, 3 retrieval-quality, and 2 efficiency checks passed.
