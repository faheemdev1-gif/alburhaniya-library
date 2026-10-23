# 2.10.17 / contract 15

This release addresses concrete causes of incomplete and weak live question searches seen in 2.10.16.

- Timeout checkpoints copy only the changed source-validated row, instead of repeatedly copying the entire growing result set. Snapshots and nested evidence remain isolated from later mutation.
- Fixed concept patterns compile before each HTTP worker becomes ready. This makes the first question avoid the fixed language-pattern compilation cost; it does not populate answer caches.
- Candidate route floors are interleaved. Requested predicate routes get an early opportunity to publish validated evidence before a deadline.
- Concept discovery generates the attached Arabic prefixes already accepted by source validation. A distinct-subject route handles overlapping concept aliases.
- A shared negative alias such as riya cannot by itself establish positive sincerity and praise-desire slots. Deliberate local relevance demotions are preserved. A small, disclosed subject-coverage signal helps specific guidance compete with broad related passages. Descriptions that explicitly state conditions for the named subject are retained as candidate property evidence.
- The same safe-index lexeme vocabulary is prepared at build time in `lexeme_spellings`, avoiding the first-request full-corpus vocabulary scan. The generated database index is `evidence-units-1.2` and must be rebuilt.
- Query plans and indexable page text are reused within each request.

The five public tool inputs and contract 15 lossless decoder remain compatible. Raw source books are preserved. Semantic models remain optional and disabled by default.

See RELEASE_REPORT.md and verification/2.10.17/ for completed local checks and their limits. This is not a deployed 10/10 certification; production metrics must be measured after deployment.
