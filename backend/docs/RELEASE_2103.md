# Al Burhaniya 2.10.3 source patch

## Corrected from the live 2.10.2 review

- Generic prayer vocabulary no longer answers a question about mobile phone
  use. A subject lacking supporting evidence produces a weak, empty result.
- Companionship discovery retains individual subject candidates and recognises
  source-attested `صحبة`/`الصحبة`/`مصاحبة` and guide language. The known b44 p43
  passage is now retrieved without a question-to-page routing rule.
- Distinct comparison subjects accept attached Arabic conjunctions. The
  sincerity/ostentation question now reaches b07 p134. When only one side of a
  comparison is available, returned pages are labelled `topic_only` and
  disclose `comparison_side`; no distinction is inferred.
- Question candidate collection is bounded to 180 source windows. Local event
  scoring uses indexed window boundaries instead of repeatedly scanning the
  full event list. The reviewed distress query finishes its declared pipeline
  in local tests.
- Cache metadata names the shared SQLite implementation and process fallback.

The original raw corpus is unchanged. The schema remains five tools at
contract 12.0. A generated database is not part of the ZIP; rebuild it with
`python scripts/build_index.py` before starting the server.

## Verification and limits

Focused regression tests, the full test suite, independent corpus audit,
public reference replay and isolated MCP HTTP results are recorded under
`verification/2.10.3/`. Public reference presence is not an independent
answer-quality grade. The owner-held private set, source review, live client
latency, schema refresh and observation window are still required for a 9+
score. No deployment or production score is claimed by this source package.

Local measurements on the final source: 235 tests passed, the corpus audit
passed, the public replay returned 30/30 nonempty results with a listed
reference in 27/30, and all 64 MCP HTTP load calls finished `full` across
1/2/4/8 client strata (16 calls per stratum). The respective local client p95
latencies were 2.28, 1.60, 2.68 and 3.79 seconds. These public questions and
the local machine are not the private evaluation or deployed environment.
