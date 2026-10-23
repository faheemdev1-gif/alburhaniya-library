# Al Burhaniya Connector 2.10.17 / contract 15

This is a tested engineering update, not a certified 10/10 service. Read
RELEASE_REPORT.md for measured results and the remaining acceptance gates.
This release reduces repeated checkpoint copying, preserves specific discovery routes, handles attached Arabic prefixes, separates shared concept aliases and builds the lexeme spelling dictionary before requests. Fixed language patterns compile during worker startup. Contract 15 input schemas and response decoding are unchanged.
The uploaded source books are unchanged. Optional semantic assets are preserved;
semantic search remains disabled by default and has not been independently graded.

## Deploy on Render

1. Replace the existing project's application files with this release. Keep your
   existing Render environment variables, endpoint and access controls.
2. Use the included Dockerfile and redeploy. It uses Python 3.12 and installs the pinned lock file,
   rebuilds library.db, runs the tests, corpus audit and token-budget gates. The generated DB
   must be rebuilt for evidence-units-1.2, including the build-time lexeme spelling table.
3. Confirm `/health` reports server_version `2.10.17`, tool_contract_version
   `15.0`, five tools, and corpus_contract.status `ok`.
4. Refresh/reconnect every MCP client so it reloads tools/list. This release retains contract 15. Contract 15 introduced
   the ultra minimal encoding (lossless-15), omits unreliable printed labels, and returns canonical raw
   get_page text so search offsets resolve exactly. Clients must use the supplied
   decoder app.services.compact_response.decode_search_response, inherited defaults,
   qasida/object tables, published codes and declared Unicode code-point coordinates.
   detail=full returns ordinary object metadata and complete digests. Ultra summary
   includes eight-character digest prefixes; compare them with the full contract.
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
   python scripts/check_token_budgets.py
   python scripts/verify_http_2116.py
   python scripts/benchmark_questions_2117.py --output verification/2.10.17/controlled_local.json

These replay disclosed development cases and measure equivalent responses. They
do not generate an independent quality score. The full JSON evidence, typed hit
schema, source hashes and test output are under verification/2.10.17/.

An independent reviewer can run evaluate_private_set.py against the deployed
endpoint, grade source spans, and pass the graded file to score_retrieval_10.py.
The stricter gate requires at least 1,002 wordings/334 intent families, explicit
negative/weak controls, >=99% Direct@5, >=95% Direct@1, label review and production
observation. It will reject missing reviews rather than manufacture a score.

Do not tell a client this release is 10/10 until those external gates are passed.

Index rebuilding now writes a separate staging database, checks integrity and publishes it atomically. Rebuild while the service is stopped; an existing journal/WAL must be recovered before replacing the target.
