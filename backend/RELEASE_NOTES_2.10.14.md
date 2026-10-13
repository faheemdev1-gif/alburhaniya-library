# Al Burhaniya Connector 2.10.14 — question-frame repairs

This is the first bounded implementation step from the 13 October engineering specifications. The five-tool contract remains 13.0, and the original source texts are unchanged.

## Retrieval changes

- Common grammatical frames for importance, stance, signs, preference, coexistence and permission now retain their intent and source subject separately. Frame words such as أهمية, موقف and علامات no longer become required source anchors. The query plan exposes `question_frame` and `requested_facets` in full detail.
- A preference using source-attested fear/hope predicates discovers the nominal concepts الخشية and الرجاء. Without an explicit directional statement in the passage, results remain `topic_only` and the response remains weak.
- A local sign cue beside the complete subject can raise a signs passage. A local negation/replacement beside an importance subject can mark a candidate as correcting the question's premise. Both remain unverified retrieval signals.
- If a recognized frame produces no supported candidate, an exact subject fallback may return scoped, `topic_only` source mentions. It never promotes those mentions to a verified answer. The fallback is recorded in the internal search state.

## Verification

- The khalwa question now finds b31 p90 at rank 1 and marks its local premise correction. The signs question now finds b07 p138 at rank 1. The stance question no longer returns empty. The preference question finds relevant fear/hope passages, but remains weak because no preferred side is established.
- Full test suite: 308 passed, one third-party deprecation warning. Independent corpus audit passed: 43 books, 6,935 pages; source files preserved.
- 31 disclosed public wordings: zero errors, 29 full question completions, no top-five or strength changes against 2.10.13; local p95 341 ms. Thirty disclosed reference cases: 27/30 references in top five, zero errors, unchanged; the three reference-page misses remain S2–S4. These checks do not grade direct answers. See `verification/2.10.14/`.

## Remaining acceptance work

This release is not a verified 9.5 or 10. The specifications also call for indexed evidence units, reviewed concept morphology, broader candidate fusion and reranking, stage diagnostics, metadata/offset contracts, and token/workflow measurements. Their blind-set thresholds and the two-release 10 gate require independent grading. The reported 27/30 reference presence is not Direct@5; plausible alternative answer pages may need review.
