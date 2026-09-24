> Historical 2.8.0 report. Current status: FIX_REPORT.md. Its figure of 15 open provenance records was incomplete.

# Al Burhania 2.8.0 remediation report

Prepared 21 September 2026. Source: the supplied 2.7.0 project, two assessments
and the recorded audit evidence. Contract: 10.0. Five tools.

## Delivery status

The updated source project passes its local automated release checks. It has
not been deployed to the live connector. This report does not certify that every
possible defect is absent or award an independent quality score.

## Verified results

| Check | Result |
| --- | --- |
| Complete pytest suite | 185 passed; one dependency deprecation warning |
| Independent structural corpus audit | Passed; no reported failures |
| Deliberately damaged stable-ID control | Corruption detected as expected |
| Fresh local HTTP MCP client | All five tools discovered and exercised; schema controls checked |
| Supplied 30-query replay | 30 nonempty responses; original reference pages in top five for 27/30 |
| Work/litanies, prayer, anger, Quran, livelihood families | Original reference pages in top five for all five phrasings in each family |
| Sadness family | Original reference page in 2/5; the other three return alternatives, including b07:180 |
| Known false relation labels | All 18 audited off-topic windows rejected as relation candidates |
| Original corpus and catalogue | Preserved; archive inventory records SHA-256 hashes |

Reference-page presence is not direct-answer accuracy. The sadness alternatives
include a passage connecting seeking forgiveness with relief of worry and distress,
but their relevance has not been independently graded in this release. The audited
queries are development fixtures and were used during implementation. Their
performance must not be represented as a held-out evaluation.

The replay's observed median local call duration was approximately 0.44 seconds.
This was a single local replay, not a controlled 30-repetition benchmark or a
production latency measurement. It does not substantiate a general speedup claim.

## Changes made

- **Citation integrity:** duplicate printed labels now include unique sequence
  locators. Original printed numbers remain unchanged and unresolved pagination is
  explicit. The two b01 locations no longer export indistinguishable citations.
- **Contents classification:** mixed-page body and contents blocks retain source
  offsets. Navigation is excluded from default matching and counts; explicit
  `include_toc=true` enables it. Poetry numbering is protected by regression tests.
- **Question retrieval:** replaced the old sentence-final-word fallback with
  compositional concepts, contextual phrases, conservative Arabic aliases,
  conversational forms and local relation checks. Source locators remain literal.
- **Relevance metadata:** preserve `answer_verified=false`, expose retained,
  dropped and proposed concepts, identify degraded/failed reformulation, and
  require opt-in for weak exploratory candidates. Proper names such as Abu
  al-Faraj do not count as evidence of relief from distress.
- **Diagnostics:** suggestions are executable retries checked against the same
  source/navigation scope. Score and pagination exclusions are distinguished when
  controlled retries establish their cause.
- **Response controls:** page limits include the ellipsis and disclose effective
  caps. Ultra-compact pages omit repeated book metadata while preserving text and
  locators. Heading stable IDs now resolve through the existing passage selector.
- **Evidence types:** search and follow-up share an explicit start-anchor scope,
  heuristic method and unverified confidence.
- **Integration:** versioned contract/digests and fresh-client checks include all
  recently added controls. Docker's build gate now runs the full pytest suite,
  including the new tests, plus the corpus audit.

## Remaining acceptance gates — not silently marked complete

1. **Production deployment and client wrappers:** the project must be deployed
   through the hosting account. Each plugin/client must refresh and demonstrate
   access to the new schema. A local server cannot update a cached external wrapper.
2. **Independent retrieval evaluation:** generalization beyond the known topic
   vocabulary remains unverified. The report's diverse 30–50-question,
   four-phrasing held-out study and 80% target have not been completed. The existing
   proposed question registry is preserved for review; no human grades were invented.
3. **Documentary provenance:** 15 unresolved catalogue records still require
   original title pages, colophons, official catalogues or transmission evidence.
   Their attributions were not upgraded without evidence.
4. **Original pagination:** unique sequence-qualified citations fix the ambiguity,
   but original scans are still needed to resolve why the printed numbers repeat.
5. **Production performance and optional vectors:** controlled repeated HTTP
   measurements and model-token comparisons remain pending. The supplied old
   vectors are retained, disabled and subject to compatibility checks; a new
   semantic model/index has not been trained or validated.
6. **Docker engine:** Docker configuration was updated, but an actual image build
   was not executed here. Python 3.12 and the real local HTTP path were tested.

These limits mean a claim that every assessment requirement is completely closed,
or that the release scores above 9, would be unsupported.

## Where to find the evidence

- `verification/final_checks.json`: current gate results and scope.
- `verification/pytest.log`: full pytest result.
- `verification/corpus_audit.log` and `negative_control.log`: structural checks.
- `verification/local_http.json`: fresh HTTP discovery and execution results.
- `verification/audit_replay_280.json`: all 30 requests and responses.
- `tests/test_release_280.py`: new defect regressions, including all 18 false labels.
- `verification/project_inventory.json`: packaged file hashes and source preservation.
- `verification/2.7.0/`: original historical verification, kept separate.

Run/deployment instructions are in `README.md` and `docs/RELEASE_CHECKLIST.md`.
