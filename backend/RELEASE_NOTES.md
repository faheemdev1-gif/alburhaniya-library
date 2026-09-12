# Al Burhania connector 2.6.0

This source release addresses the two supplied September 2026 assessments.
Tool contract: **8.0**, identifier **alburhaniya-tools-v8**, five tools.
The uploaded source is sufficient for local implementation and corpus testing.
This package has **not been deployed to the user's production service**.

## Changes and evidence

| Finding | Implementation / verification |
|---|---|
| D-1: طمأنينة silently missing | Lexeme expansion maps broad forms to actual safe-index spellings and unions article-only literal forms. All 14 literal pages remain included; 20 expanded pages are found. Literal census remains 16 occurrences. No speculative root dictionary expansion. |
| D-2: wrong or empty multi-query terms | Term attribution is constructed from the selected evidence span, with selected queries and scope declared. One match object supplies both offsets. Reordered alternatives, pagination and qasida 91/bayt 10 are regression gates. Strict terms OR alternatives are evaluated independently. |
| Partial omissions | Identity-based inclusion audits compare eligible pages before ranking, score thresholds and pagination. Reports include missing identities (bounded to 20), counts and per-query diagnostics when include_counts=true. Hybrid audits inspect its actual combined candidate set; exact candidates are no longer truncated before hybrid ranking. Equal-count substitution is a seeded test. |
| Additional confirmed spelling defect | Safe matching now recognises Persian Kaf variants already normalized by the index. Independent source counting recovered two previously missed شكر occurrences. |
| Complete context | Callable get_passage exposes paragraph mode; adjacent prose pages are assembled using source blank lines. Each segment retains source offsets and citations; the original locator remains unchanged. The character/page caps and structural stops explicitly declare incomplete context. No claim of linguistic paragraph certainty beyond the declared source-boundary policy. |
| D-3: contract clarity | Application 2.6.0 and contract 8.0 have distinct meanings. Every tool response carries release/contract metadata and request ID; successful responses also carry timings and attempts. Capability and actual callable-schema digests are distinguished. Startup validates advertised parameters and paragraph mode against the callable schema. |
| Conflicting modes | An explicit legacy search_mode selects its equivalent when match_mode=auto. Conflicting explicit selectors return invalid_request. |
| Latency / reliability | Factored phrase regexes avoid exponentially repeated whole phrases; bounded regex caching and unique-vocabulary normalization reduce repeated work. Phase timings separate candidate SQL, evidence checks, ranking, census and audit (nested timings are inclusive). Transient SQLite reads retain at most three attempts; non-transient database errors are not marked retryable. |
| Broad-question precision | Reformulations preserve original queries, expose intent coverage and a discovery warning, and require at least two original content terms. Livestock poetry no longer answers the scoped livestock-zakat question. Expert top-five relevance is not claimed as measured. |
| Payload and provenance | Ultra-compact match maps omit duplicate surface/broad fields while retaining corpus form, safe/query normalization, relation and warnings. Book provenance is preserved in the response. Heuristic evidence-type labels explicitly disclose unverified confidence. |
| Index status | Catalogue reports active semantic status, the lexeme policy version and the meaning of root annotation counts. Curated-root coverage is not a recall score. |

The actual cause did **not** require altering the conservative source index or
inventing Arabic roots. `library.db` is still reproducibly built from the supplied
source files. Source books and their attribution records are unchanged.

## Validation

- `release/regression-results.json`: full regression gate results.
- `release/protocol-verification.json`: actual local HTTP MCP discovery and execution tests, including all five tools and the corpus contract.
- `assessment-verification.json`: 36 frozen, independent source-token census cases (28 development, 8 holdout), plus five runs each of three fixed queries.
- `tests/data/assessment_literal_cases.json`: expected page identities and occurrence counts, computed independently of FTS/retrieval code under the documented article-only policy.
- The existing structural controls preserve 43 books / 6,935 pages, b38 edition handling, 95 qasidas and 2,682 abyat. Added checks sweep every stored bayt's page offsets.
- The optional real-vector integration test is skipped because local semantic search is disabled. Mocked semantic safety tests still run. No claim of live vector-model verification.

The 36 cases are **literal retrieval checks**, not 36 expert-labelled research
questions. A 30–50-question expert relevance benchmark with reviewed passages and
intent-preservation labels remains a separate editorial task. Timings are local
Python-call measurements, exclude network/production load, and are not uptime
estimates or a controlled production before/after comparison.

## Deployment

1. Replace the corresponding project files with this archive's source. For a selective update, `release/changes.patch` contains the Python changes and the new frozen fixture. Keep your deployment environment settings.
2. In the project root, install the existing `requirements.txt`, then run:
   ```bash
   python scripts/build_index.py
   python scripts/run_regression_suite.py
   python scripts/verify_assessment_release.py --runs 5 --output assessment-verification.json
   ```
3. Use the existing Docker/Render deployment workflow. The Dockerfile already rebuilds the database and runs the regression gate. No new runtime dependency or secret is required by this patch. A full Docker image build was not executed in this workspace.
4. After deployment, run:
   ```bash
   python scripts/production_mcp_regression.py https://burhaniya-library-backend.onrender.com/mcp/
   ```
5. Refresh the ChatGPT connector's tool schema. Confirm server 2.6.0, contract 8.0, five tools, and get_passage.context_mode including paragraph. If the client still caches the old schema, reconnect it.
6. Clients should compare contract version and callable-schema digest between responses. A major contract change requires refreshing tools/list before the next call; minor changes are additive. `tool_count` is a count, not a version.

## Work that needs additional evidence/access

- **Authorship/compilers:** `release/provenance-review-queue.json` records 18 entries selected by unresolved authorship, unverified confidence or needs_review status. This broader rule is not the assessment's narrower count of 15. Title-page/colophon or authoritative catalogue evidence and a review basis are required before upgrading any entry; none was invented.
- **Production incidents:** request IDs, timings and bounded retries are implemented. Explaining the previously observed internal error requires the corresponding production logs; they were not supplied.
- **Production measurements/deployment:** local protocol verification passed, but production was not modified. Deployment access and post-deploy verification are still needed.
- **Semantic quality / linguistic recall:** the safe literal inclusion property is tested. This is not proof that every morphological relative or relevant scholarly passage is recovered. Expert labels and a compatible enabled semantic index are required for those claims.
