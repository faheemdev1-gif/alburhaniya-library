# Al Burhania Library Connector 2.8.0

MCP contract **10.0** (`alburhaniya-tools-v10`), with exactly five tools.
This release addresses the supplied 2.7.0 audit. Read `REMEDIATION_REPORT.md`
for verified results and external acceptance gates. It has not been deployed
by this workspace and carries no independently awarded quality score.

## Run

Use Python 3.11 (Docker target) or 3.12:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python scripts/build_index.py
python scripts/finalize_verification.py
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The database is generated from the included original sources. Stop the service
before rebuilding: the builder replaces `library.db`. No corpus text or
attribution has been silently rewritten. The corpus contains 43 books, 6,935
pages, 95 qasidas and 2,682 bayts. Default edition scope remains 42 books and
6,885 pages; default evidence matching now excludes navigation blocks within
that scope.

Health: `/health`. Streamable HTTP MCP: `/mcp/`.

```bash
docker build -t alburhaniya:2.8.0 .
docker run --rm -p 8000:8000 alburhaniya:2.8.0
```

The image builds the index, runs the full pytest suite (including the new audit
regressions), and runs the independent corpus audit. The Docker engine itself
was not available for verification in this workspace; local Python and HTTP
checks are reported separately.

## Contract changes

- Repeated printed-page labels keep the source number and add an unambiguous
  sequence locator. `pagination_status` flags unresolved repeated pagination.
- Mixed pages expose offset-preserving body/contents blocks. Search and census
  exclude contents by default. Set `include_toc=true` for a navigation-inclusive
  census, including comparisons with the old 2.7.0 counts.
- The question planner preserves explicit concepts and local relational clues.
  It includes versioned Arabic vocabulary and conversational forms. It is a
  conservative lexical system, not a general semantic model. Its known-audit
  results are not evidence of generalization to unseen topics.
- Question results declare `answer_verified=false`. `relation_candidate` means
  local lexical relation evidence, not a confirmed answer. Weak results require
  `include_topic_only=true`. Unknown relationships can return no default results;
  inspect the plan and the verified exploratory retry.
- `reformulation_status`, preserved/dropped concept metadata and source-local
  evidence offsets explain the planner's limits.
- Empty-result diagnostics identify score, pagination or relation filtering
  when a successful controlled retry proves that cause. Other empty responses
  remain `matching_or_scope`; they do not assert absence from the corpus.
- `get_page(max_chars=100)` respects that character budget, including ellipsis.
  It reports requested/effective caps. `ultra_compact` preserves text and citations
  and omits repeated book metadata; retrieve full provenance with `get_book`.
- Qasida headings such as `b14-q007-h` work with `get_passage(stable_id=...)`.
- Search and passage evidence types share a disclosed `start_anchor` scope and
  retain heuristic/unverified metadata.

Full paragraph controls, exact/lexeme inclusion checks, explicit edition
selection, qasida structure and unverified parallel-candidate warnings remain.
Optional semantic vectors are retained unchanged for traceability and remain
disabled: regenerate and evaluate compatible vectors before enabling them.

## Verification and deployment

`verification/final_checks.json` records the current checks. The original release's
logs are preserved under `verification/2.7.0/` and are historical evidence only.
Use `scripts/finalize_verification.py` for this release, not the legacy 2.7.0
benchmark commands. `tests/data/audit_270_regressions.json` freezes the 30 supplied
queries; `audit_270_false_relations.json` preserves all 18 reviewed false labels.

After deployment, run:

```bash
python scripts/production_mcp_regression.py --endpoint https://YOUR-HOST/mcp/
```

Refresh connector discovery in each supported client. The server cannot replace
a plugin's cached wrapper schema. Consult `docs/RELEASE_CHECKLIST.md` for the
required post-deployment checks and independent review.
