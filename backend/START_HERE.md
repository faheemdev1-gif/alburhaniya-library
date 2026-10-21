# Al Burhaniya Connector 2.10.15 / contract 14

This is a tested engineering update, not a certified 10/10 service. Read
RELEASE_REPORT.md for measured results and the remaining acceptance gates.
The uploaded source books are unchanged. Optional semantic assets are preserved;
semantic search remains disabled by default and has not been independently graded.

## Deploy on Render

1. Replace the existing project's application files with this release. Keep your
   existing Render environment variables, endpoint and access controls.
2. Use the included Dockerfile and redeploy. It installs the pinned lock file,
   rebuilds library.db, runs the tests and the corpus audit. The generated DB
   must be rebuilt; a 2.10.14 DB is not compatible with the new evidence units.
3. Confirm `/health` reports server_version `2.10.15`, tool_contract_version
   `14.0`, five tools, and corpus_contract.status `ok`.
4. Refresh/reconnect every MCP client so it reloads tools/list. Contract 14 changes
   the ultra aliases, omits unreliable printed labels, and returns canonical raw
   get_page text so search offsets resolve exactly. Clients must use the supplied
   decoder map, result_defaults and declared Unicode code-point coordinates.
5. Run the deployed smoke check:

   python scripts/production_mcp_regression.py https://YOUR-HOST/mcp/

For native Python deployments, use:

   python -m pip install -r requirements-lock.txt
   python scripts/build_index.py
   python -m pytest -q
   python scripts/independent_corpus_audit.py library.db
   python scripts/start_server.py

The hosting platform supplies PORT. WEB_CONCURRENCY defaults to 2. No embedding
model download, vector service or new API key is required for default retrieval.

## Durable monitoring

All tool attempts are recorded separately from scheduled probes. The default
/tmp stores disappear on container replacement. For production acceptance,
mount persistent storage and configure writable paths, for example:

   TRAFFIC_METRICS_PATH=/var/data/alburhaniya-traffic.sqlite3
   MONITOR_SUMMARY_PATH=/var/data/alburhaniya-monitor-history.json

A free ephemeral container alone cannot establish seven-day durable monitoring.
An external collector can also retain the build-tagged `tool_attempt` logs;
deduplicate by request_id. Scheduled probes alone are not all-traffic evidence.

## Verification and review

   python scripts/verify_engineering_2115.py
   python scripts/measure_workflow_2115.py

These replay disclosed development cases and measure equivalent responses. They
do not generate an independent quality score. The full JSON evidence, typed hit
schema, source hashes and test output are under verification/2.10.15/.

An independent reviewer can run evaluate_private_set.py against the deployed
endpoint, grade source spans, and pass the graded file to score_retrieval_10.py.
The stricter gate requires at least 1,002 wordings/334 intent families, explicit
negative/weak controls, >=99% Direct@5, >=95% Direct@1, label review and production
observation. It will reject missing reviews rather than manufacture a score.

Do not tell a client this release is 10/10 until those external gates are passed.
