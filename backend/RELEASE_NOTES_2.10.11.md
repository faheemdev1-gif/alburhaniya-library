# Al Burhaniya Connector 2.10.11 — evidence and query repair

This source package builds on the supplied 2.10.10 code and preserves the book source texts. The version bump invalidates the shared result cache for the changed ranking and evidence labels. The five-tool contract remains 12.0.

## Changes

- Protect the full named subject **ليلة القدر** in “كيف نحيي ليلة القدر”; the verb no longer pulls in unrelated occurrences of “revive.” Results stay topic-only unless a bounded local passage supports the observance action.
- Treat the combined merit and observance wording as two requested facets. When only merit is present, return `evidence_strength=partial` and `unresolved_facets=["observance"]` instead of implying the whole question was answered.
- Do not label fear/hope co-occurrence as an answer to “which should be preferred?” without a directional preference cue. Unresolved preference is explicit and weak.
- Make `reformulation_status=degraded` for weak or partial evidence, even when the search pipeline completed successfully.
- For a source heading that occupies its own paragraph, `get_passage(context_mode="paragraph")` preserves that boundary and supplies an `after_heading` continuation locator to the explanatory prose.
- Add an independently graded private-set scorer. It requires at least 100 intents with three wordings each, an answerability judgment, 0/1/2 review for each top-five passage, and an independent reviewer. It reports Direct@5, all-wording reliability, negative controls, candidate-label precision and client p95. It cannot certify other release gates by itself.

## Verification and limits

The local 31-wording replay is `verification/2.10.11/public_replay.json`. It had 0 errors; 29 question-form searches completed fully, while two plain lexical cases do not expose the question-completion field. A28 returns named-night passages rather than unrelated “revive” matches, but remains weak: no verified how-to passage was established. A27 remains partial. A15 is weak for the unanswered preference. This replay is a disclosed regression set, not a blind retrieval grade.

The complete test suite passed: **295 tests**. The corpus integrity audit passed for 43 books and 6,935 pages. The source text was not changed or supplemented. The 2.10.10 report’s 8.0/10 provisional score must not be upgraded from these local checks. A live deployment, independent passage grading, source additions for genuine gaps, client latency testing and seven-day monitoring remain necessary to certify 9+ or approach 10/10.

Run the local replay with `python scripts/replay_public_2111.py`. For a private set, capture with `python scripts/evaluate_private_set.py ENDPOINT INPUT OUTPUT`, have an independent reviewer fill `answerable`, `reviewer_id`, `review_status="graded"`, and `rank_grades` in the response file, then run `python scripts/score_private_gate.py GRADED_JSON OUTPUT_JSON`.
