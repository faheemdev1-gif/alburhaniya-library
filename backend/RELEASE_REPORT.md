# Al Burhaniya 2.10.16 / contract 15: verified engineering status

This release continues work that was left unfinished in the 2.10.15 handoff. It does not certify a 10/10 rating.

## Verified now

- 349 tests passed; one third-party deprecation warning.
- 18 actual HTTP/MCP smoke checks passed; eight concurrent requests had zero errors. SDK compact/minimal equivalence passed. Local client maximum: 4119 ms; cache reuse allowed.
- All 28 disclosed PDF calls returned without errors. Source-page hints appear in the top five for 18/18 checks, versus 7/18 in the uploaded baseline. This is not an independently graded Direct@5 score.
- Replay local p50 429 ms / p95 1393 ms.
- Corpus audit passed: 43 books / 6,935 pages; 95 qasidas / 2,682 bayts.
- All 44 original raw files are byte-for-byte unchanged. Seven explicit literal/lexeme controls retain their original counts and source locators.
- Token-budget gate passed, including >=25% reduction on an actual six-result lexical control with both public encodings. The one-hit question response is <=1,500 bytes.

## Additional engineering

### Canonical evidence cache

Validated full evidence is cached before compact/ultra formatting. Changing detail or expansions reuses retrieval; source quotes and provenance remain available.

### Indexed ranking inputs

42,976 units now store source-word/concept positions. Versioned rule weights use these inputs; relation routes retain a reserved candidate floor and requested predicates. This is a rule baseline, not a trained or calibrated model.

### Lossless minimal responses

Contract 15 publishes its complete decoder legend in tools/list. Shared qasida records, speaker/morphology objects and expansion inheritance remove repetition while retaining uncertainty and citation identity.

### Evidence excerpts

Visible excerpts include the complete cited span and honor the requested context. Original source text and all 44 raw files are unchanged.

### Build and monitoring reliability

Index builds publish only after commit and integrity checking. Failed builds retain the previous index. Traffic summaries isolate the current build and measure the interval actually observed.

## Measurements

Tiktoken 0.12.0; cl100k_base and o200k_base. Equivalent decoded evidence/provenance and identical returned counts are asserted. The complete decoder legend is included in measured tools/list costs; no extra metadata hydration call is needed. Payload reduction is not the reduction of an entire client conversation. The JSON includes schema discovery and a bounded follow-up (context_chars=300); proprietary client/system wrappers and Claude token counts are unavailable.

| Control | Encoding | Compact tokens | Ultra tokens | Payload reduction |
|---|---|---:|---:|---:|
| one_hit_question (1 hits) | cl100k_base | 784 | 505 | 35.59% |
| one_hit_question (1 hits) | o200k_base | 718 | 456 | 36.49% |
| five_hit_conjunction (5 hits) | cl100k_base | 2633 | 1897 | 27.95% |
| five_hit_conjunction (5 hits) | o200k_base | 2179 | 1514 | 30.52% |
| six_hit_lexical (6 hits) | cl100k_base | 2448 | 1594 | 34.89% |
| six_hit_lexical (6 hits) | o200k_base | 2016 | 1268 | 37.10% |
| census (5 hits) | cl100k_base | 2268 | 1608 | 29.10% |
| census (5 hits) | o200k_base | 1919 | 1352 | 29.55% |
| weak_negative (0 hits) | cl100k_base | 654 | 476 | 27.22% |
| weak_negative (0 hits) | o200k_base | 638 | 461 | 27.74% |

The old harness called a five-result conjunction a six-hit control. That control remains as five_hit_conjunction; a separate OR control asserts exactly six results. The one-hit control explicitly uses context_chars=40, matching the PDF example. Correct full-span excerpts explain the historical conjunction's larger compact size. The current baseline and a 5% future-growth gate ship in tests/data/token_budgets_2116.json and scripts/check_token_budgets.py; Docker builds run the measurement and gate.

## What still needs outside evidence

### Arabic/domain review

The development lexicon and weights are unreviewed. A large reviewed concept/lemma/POS set, sensitive speaker decisions, support calibration and documentary provenance require qualified reviewers and source evidence. A contextual morphology model is not claimed.

### Independent quality evaluation

Run an independently owned and graded private set. The supplied 10-tier gate requires 1,002 wordings / 334 intent families, Direct@5 >=99%, Direct@1 >=95%, per-stratum/family checks and reviewed mixed-hit labels. Public page hints are development checks.

### Deployment and observation

Render access was unavailable and this release is not deployed. Refresh real clients after deployment. Retain >=7 days / 10,000 representative attempts on durable storage and verify production latency/failure limits. No Docker daemon was available for an image-build test.

## Deployment

Follow START_HERE.md. Rebuild the database for evidence-units-1.1 and confirm server 2.10.16 / contract 15.0. Ultra summary uses lossless-15 codes/defaults/tables and short digest prefixes; use the bundled decoder or the complete tools/list guide. detail=full retains ordinary metadata and complete digests.

## Boss-ready statement

The connector has a locally verified engineering update that closes the deferred cache, encoding, retrieval-route, excerpt, build and monitoring changes. Its disclosed source-page checks and token targets pass. A 10/10 quality claim remains unproven pending independently graded Arabic/source review and production acceptance. The broader reviewed morphology/lexicon and trained calibration are not supplied by these automated tests.
