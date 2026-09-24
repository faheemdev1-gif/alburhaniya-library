# Deployment and external acceptance

Use the Render PORT launcher, correct repository root, and health path `/health`.
A port timeout and shutdown CancelledError do not identify the original cause.
Check the first startup error, command override, database path and memory limits.

At the upstream proxy, configure authenticated MCP traffic to receive machine
responses rather than JavaScript/cookie challenges. Scope exemptions to the MCP
path and authenticated/verified clients. An origin HTML guard cannot change a
response emitted before a request reaches the application. No hosting rule has
been changed by this source release.

## Scheduled monitoring

The included monitor runs 20 calls across all five tools and exits nonzero when
failure exceeds 1%. Configure an operator-owned scheduler every 15 minutes, its
alert routing, and a history path that the service can read:

```cron
*/15 * * * * cd /srv/alburhaniya && .venv/bin/python scripts/monitor_connector.py https://YOUR-HOST/mcp/ --history /srv/monitor/history.json --output /srv/monitor/latest.json
```

Set `MONITOR_SUMMARY_PATH` to that history. For a remote scheduler, configure
history replication; paths on another host do not become available automatically.
For authentication, supply `MCP_MONITOR_API_KEY` via the scheduler environment.
The contract reports sampled 24-hour success, not all-traffic availability.
Scheduling and alert delivery are not activated by including these scripts.
Run `--count 500` after deployment. Diverse question latency requires a separate
sample; the repeated monitoring question cannot certify general p95 performance.

## Client refresh

Run `python scripts/export_tool_schemas.py` or retrieve `/schemas/tools.json`.
Refresh every supported client and compare contract/schema digests. Exercise all
advertised controls with a fresh client. The local client check cannot certify a
separately cached external plugin schema. Contract 11 clients must expand defaults.

## Independent review

An owner outside development must supply 60 question IDs, at least 20 topics,
and four phrasings each (formal MSA, simple MSA, Egyptian, Sudanese). Keep the
set private; the runner expects independent_owner and questions with id, topic,
phrasing, query, and optional reference evidence:

```bash
python scripts/evaluate_private_set.py https://YOUR-HOST/mcp/ private-set.json reviewed-output.json
```

The output awaits human grades. Required thresholds: 80% direct support in top
five, 60% in each topic, 55% at rank one, <=5% empty where two content words
exist, question p95 <=8 seconds, and no public benchmark regression. Also review
200 evidence-type hits, relation precision and excerpt support. Development
replays and reference-page matches do not establish these grades.

## Documentary review

See `data/provenance_review.json` and `docs/SOURCE_REVIEW_OPEN.md`. Original title
pages, colophons, official catalogues or transmission evidence are needed before
changing attribution; record reviewer/date/basis. Prioritize b42, b01, b09, b17
and tier 5. Original scans are needed to restore b01 printed pagination; sequence
citations work now. Code cannot establish documentary authorship evidence.
