# Al Burhaniya Connector 2.10.13 — retrieval sense and evaluation gate

This update preserves the supplied source texts and the 13.0 tool contract.

- The question pipeline rejects locally attested age, size and verb readings when the user asks about the noun الكِبْر. The example query no longer ranks the former b14 p69, b13 p172 or b32 p56 false senses in the top five. This is an initial sense rule, not a complete 100-homograph model.
- A query about raising children finds attested phrases such as تربية الأبناء in the requested source scope. They remain `topic_only` and `evidence_strength=weak`: the passages are mentions, not a complete parenting answer.
- `scripts/score_retrieval_10.py` enforces the owner's 300 answerable intents with three reviewed wordings each, 50 negative and 50 weak-coverage intents, 100 reviewed homograph cases, eight answer types, graded nDCG, and the two-release gate. It refuses to produce a passing gate from a public example set or ungraded responses. The owner runs `scripts/evaluate_private_set.py` against the deployed endpoint, grades the saved responses independently, adds `ideal_top5_grades`, `wrong_sense_ranks`, `coverage_registered`, `answer_type`, `set_kind`, `homograph_case`, and externally measured public/familiar/regression gates, then scores with:

  `python3 scripts/score_retrieval_10.py graded.json report.json --previous previous_report.json`

The first run can pass the single-release gate, but not the two-consecutive-release gate. The data and grading remain with the independent owner. A 10/10 rating has not been established by this package; the held-out suite and semantic/reranker work specified in the attached plan still require measurement and development.

## Local verification

- Full suite: 304 passed, one third-party deprecation warning.
- Independent corpus audit: passed, 43 books and 6,935 pages.
- 31 disclosed public wordings: zero errors, 29 full completions, one partial-evidence response, local p95 339 ms. The only changed top-five result against 2.10.12 is the children query, which now returns weak mentions. This public replay is not independent answer grading; see `verification/2.10.13/public_replay.json`.
