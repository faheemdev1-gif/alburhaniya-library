# Retrieval correctness patch — 2026-08-19

Production configuration tested: `ENABLE_LOCAL_SEMANTIC_SEARCH=false`.

## Implemented

- Terms results now retain original-text positions and use the minimum covering
  span instead of `c0`.
- Terms ranking uses absolute coverage/proximity scoring and a larger candidate
  pool, rather than assigning the best page an automatic score of `1.0`.
- Lexical hybrid uses an absolute acceptance threshold (`0.55`) and can return
  no result when every candidate is weak.
- Contents pages are classified as `block_type=toc` during indexing and are
  structurally downranked beneath body passages.
- Sharab al-Wasl bayts are stored as structural rows with stable identifiers.
- Search results identify the exact matched `bayt_number` and `stable_id`, for
  example `b14-q091-b009`.
- Compact and ultra-compact payloads carry exact bayt metadata.

## Verified regression cases

- Qasida 91, bayt 9: exact `bayt_number=9`, `stable_id=b14-q091-b009`.
- `المحافظة الصلاة وقتها`: real local offsets; no `c0`; proximity-calibrated
  scores below `1.0`.
- `الصلاة خير من النوم` restricted to b29: no sufficiently relevant lexical
  hybrid result.
- `مشروعية الذكر للنساء` in b29: body sequence 21 ranks above TOC sequence 2.

The rebuilt database contains 43 books, 6,934 pages, and 2,679 stored bayts.
The full test suite passes with the intentionally disabled semantic-index test
reported as skipped when no `semantic_chunks` table is present.
