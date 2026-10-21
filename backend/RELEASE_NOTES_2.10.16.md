# 2.10.16 / contract 15

- **Canonical evidence cache:** Validated full evidence is cached before compact/ultra formatting. Changing detail or expansions reuses retrieval; source quotes and provenance remain available.

- **Indexed ranking inputs:** 42,976 units now store source-word/concept positions. Versioned rule weights use these inputs; relation routes retain a reserved candidate floor and requested predicates. This is a rule baseline, not a trained or calibrated model.

- **Lossless minimal responses:** Contract 15 publishes its complete decoder legend in tools/list. Shared qasida records, speaker/morphology objects and expansion inheritance remove repetition while retaining uncertainty and citation identity.

- **Evidence excerpts:** Visible excerpts include the complete cited span and honor the requested context. Original source text and all 44 raw files are unchanged.

- **Build and monitoring reliability:** Index builds publish only after commit and integrity checking. Failed builds retain the previous index. Traffic summaries isolate the current build and measure the interval actually observed.

Validation: 349 tests, 18 SDK smoke checks, 18/18 disclosed page hints, source/corpus audit and token gates passed. See RELEASE_REPORT.md for the exact scope and external acceptance gates.
