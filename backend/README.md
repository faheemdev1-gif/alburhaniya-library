# Al Burhaniya Connector 2.10.0

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
