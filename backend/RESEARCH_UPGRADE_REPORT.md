# Burhaniya Library Research Upgrade

## Implemented

- Fixed single-book pagination: diversification is automatically disabled when exactly one book is selected.
- Improved `get_passage` to prefer coherent paragraph boundaries and report truncation/page length.
- Preserved and validated multi-query `OR` / `AND` search.
- Added search modes: `exact_phrase`, `all_words`, `any_word`.
- Added ranking controls: `relevance`, `primary_first`, `chronological`, `book_order`.
- Expanded Arabic normalization for tashkil, Quranic marks, tatwil, Alef/Ya variants, Persian Yeh/Kaf forms, punctuation boundaries, and the ﷺ ligature.
- Added no-result spelling suggestions for single terms.
- Added `ultra_compact` AI response mode.
- Added maximum page-size protection to `get_page` (default 6,000 characters).
- Improved passage extraction and result highlighting.
- Added a repeatable automated benchmark and expanded unit tests.
- Rebuilt `library.db` using the improved normalization pipeline.

## Benchmark

- Unit tests: 16/16 passed
- Retrieval benchmark: 10/10 passed
- Largest indexed segment: 19,542 characters
- Duplicate page rate: 0.0%
- Standard response: 6,100 bytes
- Compact response: 5,460 bytes (13.0% smaller)
- Ultra-compact response: 4,922 bytes (25.5% smaller)

## Still requires curated scholarly data

The code now supports stronger retrieval, but the following cannot be populated reliably by generic inference alone:

- poem and bayt numbers for every work
- lecture titles and speech dates
- question numbers and volume metadata
- canonical work relationships and related-book links
- quotation/commentary/original-text classification
- OCR confidence and verified corrected-text layers

These should be supplied through a curated metadata file or verified during ingestion. They were not invented automatically.

## Deployment

Replace the previous backend with this folder and deploy normally. The included `library.db` is already rebuilt. If source files change later, run:

```bash
python3 scripts/build_index.py
python3 -m unittest discover -s tests -v
python3 scripts/benchmark_retrieval.py
```
