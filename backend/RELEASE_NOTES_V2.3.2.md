# Al Burhania connector v2.3.2

Tool contract: **5.3** (`alburhaniya-tools-v5`)  
Required public tools: exactly **5**

## Citation-integrity fixes

- Classifies explicit fihris pages and numbered dot-leader contents pages as
  `block_type: toc`; TOC results receive the existing structural penalty and
  rank below substantive body evidence.
- Reads b14 printed pages from the Dīwān's visible source footer rather than
  the inconsistent Shamela export marker.
- Adds `qasida_bayt_count` for the complete qaṣīda length.
- Keeps `bayt_from`/`bayt_to` for compatibility and adds
  `page_bayt_from`, `page_bayt_to`, and `bayt_range_scope: page` so page ranges
  cannot be mistaken for complete qaṣīda length.
- Gives heading hits deterministic identities such as `b14-q091-h`, declared
  with `stable_id_kind: qasida_heading`, instead of falsely assigning bayt 1.
- Generates `citation_label` for every indexed prose and Dīwān page and emits
  it alongside `printed_page` in compact responses.
- Makes ى/ي ambiguity warnings prefix-aware, so forms such as `هدى`/`الهدي`
  and `علي`/`العلى` are warned consistently while unrelated article-only
  normalization remains warning-free.
- Ensures strict terms results explain every FTS-proven query term even when a
  normalized source boundary falls immediately outside the minimum span.

## Deployment and verification

- Fresh Docker builds regenerate `library.db`; the generated database remains
  excluded from Git and the release ZIP.
- Existing retained databases can be upgraded with
  `python scripts/migrate_citation_metadata_v7.py`.
- Full corpus rebuild: 43 books, 6,935 pages, 95 qaṣīdas, 2,682 bayts.
- Regression result: **105 passed, 0 failed, 1 optional semantic-vector test
  skipped** because semantic vectors are intentionally not bundled.
