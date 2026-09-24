# 2.9.0, contract 11

Phrase-first and Q&A discovery; source-local ranking; sequence-only citations;
shared response defaults; bounded threaded execution; per-client quotas;
two-worker PORT launcher and schema/monitoring tools. See FIX_REPORT.md for
verified results and open external acceptance work. Refresh client schemas.

---

# Release 2.8.1 / contract 10.0

Deployment patch: Docker now starts `scripts/start_server.py`, which binds the
persistent HTTP service to `0.0.0.0:$PORT` (8000 only when PORT is absent).
It validates the port, resolves the project root and passes signals directly
to Uvicorn. Runtime startup stages are logged immediately.

See `RENDER_DEPLOYMENT.md` for existing service settings and
`../verification/2.8.1/SUMMARY.md` for validation. The reported Render failure
has not been reproduced locally, and its original cause remains unconfirmed.
The patch has not been deployed to Render by this workspace. Retrieval and
source-verification acceptance gates from 2.8.0 remain open.

---

# Release 2.8.0 / contract 10.0

| Audit defect | Implementation | Verification |
| --- | --- | --- |
| D-1 duplicate citations | Preserve printed number; qualify repeated labels with unique sequence; expose pagination uncertainty | Both b01 locations and passage round trips |
| D-2 mixed contents/body | Typed blocks at ingestion, source offsets preserved; explicit navigation opt-in; matching/count scope aligned | b41:154 body and TOC, scope reset, poetry negative control |
| D-3 fragile reformulation | Compositional concepts, contextual phrases, conversational forms, local evidence windows, function-word exclusions | 30 supplied development phrasings; not an unseen-topic accuracy claim |
| D-4 false relation labels | Require local relation clues; exclude proper-name homographs; preserve unverified status; weak-candidate opt-in | All 18 audited false relation labels |
| D-5 stale wrapper schemas | Contract version/digests; stricter fresh-client schema/execution checks | Local fresh HTTP client; deployed plugin wrappers still require refresh/testing |
| D-6 misleading retries | Executable retry checked within the same source/navigation scope; filter-aware diagnosis | Score-filter and pagination retries execute successfully |
| D-7 page response shape/cap | Real ultra-compact projection; exact cap including ellipsis; requested/effective limits | Caps 1, 100, 1,000, 20,001 and citation/text equivalence |
| D-8 evidence-type mismatch | Start-anchor classification shared by search and follow-up; method/confidence retained | Search/passage metadata comparison |
| Heading stable IDs | Resolve qasida headings through existing stable selector | b14-q007-h; invalid selectors reject consistently |

Raw source texts and provenance are preserved. No `direct_answer` label is emitted:
there is no independent answer-verification component. Provenance authentication,
live client refresh, deployment and independent held-out grading remain external
acceptance gates. See the root remediation report for actual check results.
