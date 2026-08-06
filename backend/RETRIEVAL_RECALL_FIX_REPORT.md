# Burhaniya retrieval recall and citation upgrade

## Fixed

1. **Silent lexeme under-retrieval**
   - Added `search_mode="lexeme"` for a single Arabic lexeme per query.
   - It expands common Arabic proclitics (`ال/و/ف/ب/ل/ك` and combinations),
     attached suffixes, and weak-final `ي/ا` forms.
   - Ordinary `exact_phrase` remains the default, preserving precision.
   - Diagnostic: exact `حمى` in `b14` still reports 7 matching pages; lexeme
     mode returns a recall-oriented superset of the established 16-page
     enumerated-variant census.

2. **Unambiguous census semantics**
   - `total_hits_unit` is now explicitly `matching_pages`.
   - Added `total_occurrences`.
   - Added `per_query`, with independent `matching_pages` and `occurrences`
     for every supplied alternative.
   - Overlapping alternatives are deduplicated in the aggregate occurrence
     count.

3. **Citations for b44/b45**
   - Preserved the source `page_label` during indexing as `citation_label`.
   - Search, `get_page`, and `get_passage` return this label when a printed
     page is unavailable (for example `حولية 2004 — مقطع 1` or `خطاب 1994`).

4. **Five-level evidential hierarchy**
   - Added machine-readable `tier: 1..5` to every catalogue/search/page item.
   - Tier definitions are returned with `list_books(include_legend=true)`.
   - `b26–b30` are tier 2; `b42`, `b44`, and `b45` are tier 3.
   - Binary `primary/secondary` remains for backward compatibility.

5. **Single-book SQL regression**
   - The existing qualified `p.book_id` filters are retained.
   - Regression coverage confirms selected-book searches are neither
     ambiguous nor silently diversified/truncated.

## Verification

- Rebuilt `library.db`: 43 books, 20 primary, 23 secondary, 6,934 segments.
- b34/b35 remain absent; b44 has 57 segments; b45 has 19.
- 20 automated regression tests pass.
- Python compilation passes for application, scripts, and tests.

## Deployment and schema refresh

Deploy this package normally; the Docker build runs `scripts/build_index.py`.
After the deployment is healthy, refresh the Burhaniya app actions in ChatGPT.
Start a new conversation and verify that `get_passage`, `queries`, `search_mode`,
`ranking`, `diversify_books`, tier metadata, and census fields are visible.
Disconnect/reconnect only if refreshing actions does not expose the new schema.
