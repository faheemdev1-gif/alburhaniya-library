# Release and reassessment checklist

## Local checks supplied with this project

- Rebuild the corpus from the 43 mapped books and confirm 6,935 pages.
- Run all unit, full-tool-boundary, negative-control and corpus integrity checks.
- Compare the four fixed local query benchmarks with 2.6.0 and retain result IDs.
- Discover all five tools from a fresh MCP client and check contract 9.0.
- Measure first-request and warm server/client timings, retry attempts and tokens.
- Confirm old semantic vectors cannot silently activate on the new corpus.
- Read the generated logs/reports in `verification/`; do not infer success from test count alone.

## Before replacing the live release

1. Preserve the deployed commit/image ID and environment settings for rollback.
2. Build/test this project using Python 3.11 and the supplied Dockerfile.
3. Keep local semantic and legacy external engines disabled unless separately tested.
4. Deploy through the existing authorised deployment workflow.
5. Confirm `/health` reports server 2.7.0, contract 9.0, five tools and corpus status ok.
6. In a fresh ChatGPT/Claude session, refresh tools/list and call all five tools.
7. Repeat paragraph request `b11-p132-c304` with `context_mode=paragraph`; verify
   segment offsets, printed-page citations, truncation and completion together.
8. Search the livelihood fixture and the prayer-timing fixture; inspect expanded
   source passages, not just scores. Repeat exact/lexeme identity checks.
9. Run `scripts/production_mcp_regression.py --help` and use its endpoint option
   against the deployed connector. It makes read-only requests; do not infer
   production availability from the local stdio check.
10. Measure at least 30 repeated samples per fixed query on the deployed HTTP path;
    separate first-request/warm caches and client/server p50/p95, record load/retries.
11. Keep one stale client session open during deployment, observe its digest/version
    change, refresh tools/list, and verify successful recovery. The server cannot
    refresh a client's cached schema on its behalf.

## Independent assessment still required

- Reviewer grades the 24 development questions, then the 16 held-out questions
  after tuning is frozen; record page identities, relevance labels and rationale.
- Resolve documentary attribution from title pages, colophons or official evidence;
  preserve unresolved status where evidence is insufficient.
- Request a fresh assessment using the same weighted rubric as the supplied reports.
  A local test pass is not a guaranteed score above 9.

Rollback: redeploy the preserved previous image/commit through the normal workflow.
Do not overwrite source texts or reuse incompatible index/vector artifacts.
