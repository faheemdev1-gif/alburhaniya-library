# Al Burhaniya 2.10.17 - changes and verification

This is a new code update prepared after the live 2.10.16 retest. It is ready for deployment; these results are local verification, not new production scores or a 10/10 certification.

## Why the live results were not improving

The repeated tests were running the same deployed build. Its question searches frequently stopped near the five-second pipeline budget. Investigation found repeated copying of the growing evidence set for timeout checkpoints, cold language-pattern compilation, inconsistent handling of attached Arabic prefixes, and related concept aliases that could satisfy two subject slots with one word. The first lexeme request also constructed the vocabulary by scanning the corpus.

Those are concrete application costs and retrieval gaps. The retest did not prove that hosting alone caused them, or establish the cause of every connection failure.

## Changes made

- Publish one changed source-validated row per checkpoint, preserving nested snapshot isolation and thread safety.
- Compile the fixed language patterns before an HTTP worker becomes ready; this does not populate answer caches.
- Interleave candidate-route floors so requested predicates can yield validated evidence before a deadline.
- Generate the attached Arabic prefixes already accepted by source validation, and retain routes with distinct subject evidence.
- Require positive sincerity evidence separately from a shared negative alias such as riya. Preserve deliberate relevance demotions.
- Retain specific subject coverage and explicit conditions describing the named subject, using disclosed development rule signals.
- Build the same safe-index lexeme spelling dictionary during indexing, and reuse query plans and indexable page text within a request.

The tools retain contract 15 and its lossless decoder. The new index is evidence-units-1.2. Rule weights remain unreviewed and uncalibrated; this release does not introduce a trained ranking model.

## Completed verification

| Check | Result |
|---|---|
| Full automated suite | 358 passed; no failures |
| Actual local HTTP/MCP SDK smoke checks | 18 passed |
| Eight concurrent local SDK requests | No errors; maximum client time 2.68 seconds |
| SDK compact / ultra equivalence | Passed |
| Disclosed 28-case replay | 0 errors; 26 full searches; 0 partial searches |
| Expected source page in top five, disclosed hints | 18/18 |
| Returned search quotations and text-version hashes | 102/102 matched the supplied canonical text |
| Literal / lexeme / count regression controls | 7/7 retained prior counts and locators |
| Corpus integrity audit | Passed: 43 books, 6,935 pages, 95 qasidas and 2,682 bayts |
| Source files and source metadata | 46 protected files unchanged from the delivered 2.10.16 archive |
| Token-budget gate | 10 controls passed |
| Six-hit ultra-compact token savings | 34.87% with cl100k_base; 37.06% with o200k_base |

Source fidelity verifies the supplied text, not its documentary authenticity or the correctness of an answer. The page hints are disclosed development fixtures, not independently graded Direct@5.

## Controlled local comparison

Both code versions used the same corpus and precompiled fixed language patterns, with no answer-cache reuse. Eighteen disclosed questions ran three times per budget. P95 uses nearest rank.

| Metric | Original 2.10.16 code | Final 2.10.17 code |
|---|---:|---:|
| Normal five-second budget: source-page hits | 54/54 | 54/54 |
| Normal budget: complete searches | 54/54 | 54/54 |
| Normal budget: p95 | 689.0 ms | 547.8 ms |
| Artificial 0.25-second budget: source-page hits | 48/54 | 52/54 |
| Artificial budget: partial searches | 45/54 | 44/54 |
| First scoped lexeme check | 1170.1 ms | 853.1 ms |

The measured p95 reduction was 20.49%; the first scoped lexeme check was 27.09% faster. The 0.25-second condition is a synthetic stress test, not an emulation of Render. Most searches remained partial under that artificial deadline. The final run missed the restart-practice hint twice under that short budget; the normal-budget runs recovered it.

A preliminary updated-code run, before the final property-condition ranking adjustment, measured a 24.03% p95 reduction and 54/54 stress hits. The final run above is used for the release figures to disclose timing variability rather than select the strongest run. Local timings do not guarantee a particular production improvement.

## Deployment

1. Replace the application files with this release and keep the existing access keys and hosting environment settings.
2. Redeploy with the included Dockerfile. It rebuilds library.db with the new lexeme spelling table and runs tests and integrity/token gates. Do not reuse an old generated database.
3. Confirm /health reports server_version 2.10.17, tool_contract_version 15.0, five tools, and corpus_contract.status ok.
4. Refresh the MCP client and run the live suite against the new build.

This complete ZIP includes code, source texts, tests, instructions, verification evidence and both preserved optional semantic vector assets. Those assets are unchanged from the full 2.10.16 package and have not been newly trained or independently benchmarked. Local semantic search remains disabled by default.

The production service has not been replaced through this workspace. The last measured live 2.10.16 run still stands: 15/18 expected source-page hits, 13/26 partial searches and 1/28 failed requests. Production error rates, deadlines and latency must be checked after deployment. A verified 10/10 assessment also requires independently owned and graded Arabic questions and sustained production observation.

## Reproduce and inspect

- `python -m pytest -q`
- `python scripts/verify_engineering_2115.py`
- `python scripts/verify_http_2116.py`
- `python scripts/independent_corpus_audit.py library.db`
- `python scripts/measure_workflow_2115.py`
- `python scripts/check_token_budgets.py`
- `python scripts/benchmark_questions_2117.py --output verification/2.10.17/controlled_local.json`

The comparison script accepts --baseline-code pointing at a folder containing the earlier app package. Raw per-case outputs, both comparison runs, source checks, test output and protocol results are under verification/2.10.17/. RELEASE_MANIFEST.json records the packaged file hashes.
