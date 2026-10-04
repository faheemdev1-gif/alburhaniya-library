# Al Burhaniya Connector 2.10.7

This release broadens Arabic question understanding for comparisons, reward,
companionship, dream vision and smoking vocabulary. It keeps unsupported
smoking mentions weak and preserves literal census rules. It retains the
2.10.6 candidate bound and counted monitoring probes. See
`docs/RELEASE_2107.md` for local checks and independent grading requirements.

## Previous 2.10.6 corrections

Live 2.10.5 cold searches still skipped scoring on four broad livelihood and
distress prompts. This patch bounds those intents to 40 source windows and
uses uncached scheduled search probes. The larger pool for other subjects and
the five-tool contract remain unchanged. See `docs/RELEASE_2106.md`.

The live 2.10.4 search still skipped scoring on broad livelihood and distress
questions. This release caps only those intent groups at 80 passage candidates,
retains 120 for other subjects and labels incomplete scheduled search probes
as monitor failures. See `docs/RELEASE_2105.md` for verification and limits.

This patch bounds question passage candidates at 120 windows (60 per FTS
expression). The live 2.10.3 distress query reached the former 180-window
limit and repeatedly declared partial after a 4.5-second scoring stage. The
public 30-question replay retains 27/30 listed reference pages and all 30
complete locally with the new cap. See `docs/RELEASE_2104.md` for measured
limits and deployment checks.

This release repairs the live 2.10.2 retrieval regressions: it protects the
requested subject in generic questions, discovers the companionship passage
on b44 p43, keeps both comparison subjects when Arabic conjunctions are
attached, and labels one-sided comparison evidence as weak. Question scoring
uses a bounded candidate union and a source-local event index. The five-tool
contract remains 12.0. See `docs/RELEASE_2103.md` for local verification and
open acceptance gates.

## Previous 2.10.2 corrections

This source patch carries source-local attribution guards across search,
`get_passage` and `get_page`, recognises additional comparison frames, removes
the redundant `alternate_locations` response field, and uses a bounded SQLite
result cache across the default two worker processes. The cache defaults to
`/tmp/alburhaniya-result-cache.sqlite3`; set `RESULT_CACHE_PATH` to a writable
shared local path if needed. The cache key includes the release version,
request controls, corpus identity and navigation scope. The five-tool MCP
contract remains 12.0.

The 9+ target remains an acceptance target. See `docs/RELEASE_2102.md` for
completed checks and the independent work still needed to assign a score.

## Previous 2.10.1 corrections

This patch fixes the live 2.10.0 audit regressions: comparison questions now
require both distinct subject terms in one local passage; interrogative `ما`
is no longer reported as negation; `literal_*` count fields use source surface
forms while `normalized_*` fields retain the article-aware census; paragraph
context is bounded to three pages; and the b37 compiler note agrees with its
metadata. The five-tool MCP schema and contract major version remain unchanged.
The corrected release must be deployed and independently graded before a 9+
retrieval rating can be claimed.

This release implements the 2.9 developer report's engineering corrections. It is a tested source package, not a deployed or independently scored release. **A final 9+ score is not certified.**

The complete 32-item acceptance matrix is in `verification/2.10.0/issue_matrix.json`. The PDF completion report explains the measurements and remaining gates. Historical 2.7/2.8/2.9 reports are retained as historical evidence only.

## Run and deploy

Use Python 3.11 or 3.12 from this project directory:

```bash
pip install -r requirements-dev.txt
python scripts/build_index.py
python -m pytest -q
python scripts/independent_corpus_audit.py library.db
python scripts/start_server.py
```

Docker performs the index build and regression gate. The launcher honors `PORT` and `WEB_CONCURRENCY` (default 2). Health is `/health`; MCP is `/mcp/`; callable schemas are `/schemas/tools.json`. Rebuild the database: the archive deliberately excludes generated `library.db`. Optional semantic vectors are retained but remain disabled by default.

## Monitoring and clients

The launcher starts a five-minute monitoring process unless `MONITOR_ENABLED=false`. `MONITOR_SUMMARY_PATH` defaults to `/tmp/alburhaniya-monitor-history.json`. Set it to a persistent service path if seven-day history must survive a restart. The helper uses the existing configured API key without printing it. Running Uvicorn directly bypasses launcher supervision; start `python scripts/monitor_service.py` separately in that case.

Refresh the connector's tool definitions separately in ChatGPT and Claude after deployment. Reconnect/re-add the connector if that client retains its old schema, then run all nine controls listed in `docs/CLIENT_ACCEPTANCE_2100.md`. A server cannot invalidate another application's cached tool schema by itself.

Optionally set `CLIENT_SCHEMA_DIGESTS` to a JSON object mapping verified client names to the digest from their fresh tools/list. Startup rejects a configured mismatch. An absent mapping does not imply client verification.

## Verification

- `python scripts/acceptance_2100.py`: 5 response-cache-cold and 5 warm trials for 24 report questions, 30 bare phrases, census and payload checks.
- `python scripts/load_2100.py`: real local MCP HTTP at 1/2/4/8 concurrent clients, plus nine-control protocol calls.
- `python scripts/verify_release_2100.py`: public 30+11 question replay, **reference presence rather than answer accuracy**.
- `python scripts/measure_payload_2100.py`: named-tokenizer comparison with frozen source evidence.
- `python scripts/evaluate_private_set.py ENDPOINT PRIVATE_INPUT OUTPUT`: owner-held 40-question evaluation; results require independent grades.

## Open acceptance gates

Live deployment and per-client refresh, seven days of production monitoring, the owner-held private question set, 100-hit human relevance/type grading, full best-phrase/top-ten and tie checks, and unresolved documentary/scan reviews remain open. These are not marked resolved by a successful unit test. Raw Arabic source files are byte-for-byte preserved. Four metadata updates have exact documentary excerpts in `data/provenance_decisions_2100.json`; no source tiers were upgraded.
