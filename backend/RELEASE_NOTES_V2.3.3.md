# Al Burhania connector v2.3.3

Tool contract: **5.4** (`alburhaniya-tools-v5`)  
Required public tools: exactly **5**

## Contents-page false-positive fix

- Removed dot-only TOC detection. Decorative omissions, poetry caesuras, and
  footnote separators are no longer treated as index evidence.
- Implicit index pages must contain repeated dotted leaders followed by
  destination page numbers, sufficient entry density, and occur in front or
  back matter.
- Explicit contextual headings such as `فهرس الجزء` remain authoritative;
  incidental prose mentions of `الفهرس` do not.
- Restored b29 sequence 35 to `block_type: body`, so its teaching on sūrat
  al-ʿAṣr and sūrat al-Insān is no longer structurally downranked.
- Corpus-wide reclassification reduced `toc` labels from 1,105 to 67. Genuine
  samples b29 sequences 2–5 and b12 sequence 271 remain classified as `toc`.
- Added hard regressions for decorative dots, required trailing page numbers,
  plausible TOC location, and the full set of classified TOC pages.

## Retrieval stability

- Widened the internal hybrid candidate pool from a minimum of 40 to 80 after
  restoring falsely penalized body pages. The public threshold, calibration,
  and final result limits are unchanged.

## Verification

- Fresh rebuild: 43 books, 6,935 pages, 95 qaṣīdas, 2,682 bayts.
- TOC audit: 67 classified pages; b29 sequence 35 is `body`.
- Regression result: **109 tests, 0 failures**; 1 optional semantic-vector
  test skipped because semantic vectors are intentionally not bundled.
- Gate totals: 103 hard, 3 retrieval-quality, and 2 efficiency checks passed;
  `deployment_blocked: false`.
