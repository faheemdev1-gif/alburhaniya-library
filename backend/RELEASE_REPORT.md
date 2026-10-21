# Al Burhaniya 2.10.15: local verification and acceptance status

**Verdict: tested engineering update; no certified 10/10 rating.** This build has not been deployed to the user's Render service. All performance observations below are local.

## Measured checks

- 332 automated tests passed; one third-party deprecation warning.
- Corpus audit passed: 43 indexed books / 6,935 pages, 95 qasidas / 2,682 bayts.
- 44 original raw source files compared byte-for-byte with the uploaded archive; none changed.
- 28 disclosed PDF calls: 0 errors. Source-page hints present in top five: 17/18, versus 7/18 in the uploaded baseline. This is not Direct@5.
- Local sequential replay p50 377 ms / p95 1319 ms, measured by the bundled replay script.
- 7 explicit literal/lexeme controls retain their original counts and source locators.
- Full HTTP/MCP validation passed 18 smoke checks. Eight simultaneous local requests returned 0 errors; cache reuse was allowed.
- Canonical page text, source-slice validation, compact/ultra evidence equivalence and supervisor checkpoint cancellation have executable tests.

## Fixes and limits

| Ticket family | Code in this release | Acceptance still open |
|---|---|---|
| R-01 | 42,976 source-coordinate paragraph / Q&A units, stable unit hashes, heading/section links. | Independent evidence-unit boundary review, especially cross-page structures. |
| R-02 | Question frames, protected subjects, alternatives, negation and conditional/coexistence metadata. | Reviewer-labelled intent/slot accuracy and independently written dialectal variants. |
| R-03 | Small typed discovery lexicon, source-attested candidate vocabulary, no literal-count expansion. | 600 reviewed concepts, large inflection/POS evaluation and domain link review; no contextual morphology model was added. |
| R-04 | Bounded route-family RRF, no phrase-only early return, source routes/caps/manifests in audit detail. | Candidate AnswerSpanRecall on private families; current final cap is 160 units. |
| R-05 | Source-local relation, premise correction, explicit procedural-list and comparison features. | A trained/calibrated reranker and independent direct/indirect/topical judgments; local span scoring remains. |
| R-06 | Visible source excerpts and exact source quotes; answer_verified remains false. | Independently approved answering spans and support-label calibration. |
| R-07 | Supervisor-visible validated checkpoints; global bounds and cooperative SQLite/stage cancellation. | Broad production failure injection/load; canonical candidate-cache redesign is not claimed (existing safe projection-bound cache remains). |
| D-01 | Separate execution/evidence status; empty budget endings remain unknown/unrecovered. | Independent outcome/trace audit under representative production conditions. |
| D-02 | Retries retain the original question and scope; no subject-dropping retry asserted as an answer. | Independent usability and recovery grading. |
| D-03 | Stage-start/checkpoint events, exclusive timings, build-tagged all-tool metrics. | Durable mount/external log retention and seven days of observed traffic. |
| D-04 | Existing faithful literal postings/counts preserved; locator/count controls checked. | Private scoped recall comparisons beyond the disclosed controls. |
| T-01 | One canonical compact projection, reversible ultra mapping and typed source validation. | Cached real clients must refresh and exercise contract 14. |
| T-02 | Existing result defaults preserved; routine successful tracing removed from summary; duplicate quote text kept only in full detail. | Full qasida-table normalization and the requested size-reduction target are not claimed. |
| T-03 | cl100k_base and o200k_base measurements, equivalent evidence and discovery + follow-up costs. | 25% reduction not demonstrated; actual Claude/client wrapper usage unavailable. |
| M-01 | Shared Pydantic source/span/speaker/support types plus exported JSON Schema. | Independent mixed-hit metadata review. |
| M-02 | Explicit/structural speaker evidence, separate anchor/passage scope and preserved opponent warnings. | Sensitive-speaker and source-role editorial validation. |
| M-03 | Canonical get_page text; code-point/half-open source spans, SHA/version and slice checks. | Original scan verification where documentary uncertainty remains. |
| M-04 | Existing paragraph/section/cross-page reads retained; heading slice trimming inconsistency removed. | Broader private section/cap/continuation acceptance. |
| M-05 | Callable declarations drive advertised parameter lists; live tool schema digests and local SDK checks. | Every real client must refresh tools/list after deployment. |

## Token/workflow measurements

Tokenizer: tiktoken 0.12.0. Mandatory evidence, provenance and follow-up context are equivalent. These are public encoding profiles, not billed-model or Claude usage.

| Control | Encoding | Compact | Ultra | Payload reduction |
|---|---|---:|---:|---:|
| one_hit_question | cl100k_base | 809 | 762 | 5.81% |
| one_hit_question | o200k_base | 735 | 688 | 6.39% |
| six_hit_lexical | cl100k_base | 2421 | 2301 | 4.96% |
| six_hit_lexical | o200k_base | 2063 | 1943 | 5.82% |
| census | cl100k_base | 2273 | 2159 | 5.02% |
| census | o200k_base | 1924 | 1811 | 5.87% |
| weak_negative | cl100k_base | 656 | 647 | 1.37% |
| weak_negative | o200k_base | 641 | 633 | 1.25% |

**The requested 25% token reduction has not been established.** The JSON report includes full discovery + follow-up costs and zero metadata-hydration calls.

## What is needed to close acceptance

1. Deploy and pin this exact build; refresh real client schemas. The local Python hosting entry point and HTTP/MCP boundary were tested; a Docker daemon and Render account access were unavailable.
2. Have an independent owner run and grade private families. The stricter included 10-tier gate requires 1,002 wordings / 334 intent families, Direct@5 >=99%, Direct@1 >=95%, strata/families >=97%, explicit negatives and reviewed support labels. Public cases are development data.
3. Provide Arabic/domain editorial review, original scans/provenance decisions and at least 1,000 reviewed mixed hits. No human review identity, calibration probability or scan verification was fabricated.
4. Retain durable all-traffic production metrics for >=7 days / 10,000 representative attempts, and verify the latency/failure thresholds. /tmp and scheduled probes alone do not prove continuity.
5. Review the hinted-page misses (F13_LOVE). Other source candidates may be sufficient; the developer has not self-awarded answer grades.

## Client compatibility

Contract 14 deliberately changes the public coordinate and ultra-projection rules. get_page returns unformatted canonical source text; unreliable printed labels are omitted; ultra fields are decoded using the published alias map and result_defaults. Routine successful trace/census-not-checked detail requires detail=full. Existing tests were updated only where these intentional contract rules changed; retrieval/source controls were retained.

## Boss-ready statement

> The connector has a tested engineering update with preserved sources and improved disclosed-case retrieval. It is ready for deployment verification. A 10/10 quality claim remains unproven pending independent grading, editorial/source review and production evidence.
