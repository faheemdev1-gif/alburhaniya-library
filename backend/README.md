# Al Burhania Connector 2.9.0

Five MCP tools; contract 11.0. See `FIX_REPORT.md` for the status of every
assessment item. This package has not been deployed to Render here.

## Run

Python 3.11 (Docker target) or 3.12:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python scripts/build_index.py
python -m pytest -q
python scripts/independent_corpus_audit.py library.db
python scripts/start_server.py
```

The original texts and catalogue are included. The generated `library.db` is
built from them; it is intentionally excluded from the ZIP. Stop the service
before rebuilding. The launcher validates the database and discovery schema,
binds `0.0.0.0:$PORT` (8000 locally), and starts two workers by default.

Health `/health`; MCP `/mcp/`; callable schemas `/schemas/tools.json`.
Docker builds run the index builder, full pytest suite and corpus audit.
An actual Docker build/Render deployment remains unverified in this environment.

## Contract 11 migration

Search hits inherit `result_defaults`. Explicit hit values override defaults:

```python
hits = [{**response.get('result_defaults', {}), **hit}
        for hit in response['results']]
```

`detail="full"` retains query/intent/normalization traces; summary is the default.
`keep_terms=[...]` preserves selected words in the planner. Dropped function words
are disclosed. Ultra-compact books carry ID/tier; get_book supplies attribution.
Compact summary keeps titles, source tiers, attribution confidence and provenance status; detailed authorship/compilation fields remain in detail=full or get_book.
Citations and excerpts remain in all modes. Near-duplicates keep alternate_locations.

Question discovery retains exact subject-phrase witnesses, adds passage/Q&A and
morphological candidates, and uses corpus-derived topic proposals. These are
candidate sources, not verified answers. `answer_verified` stays false.
The topic proposals are unreviewed; Q&A segmentation is within-page only.
Optional semantic vectors remain disabled pending independent evaluation.
Repeated unreliable printed labels use sequence-only citations without inventing
original page numbers or changing attribution.

## Runtime settings

- `WEB_CONCURRENCY=2`, valid range 1–8.
- `REQUEST_BUDGET_SECONDS=18`, execution capped below 20 seconds.
- `MCP_REQUESTS_PER_MINUTE=2400`, per authenticated client or peer IP.
- `MCP_API_KEYS`: optional comma-separated Bearer keys. Configure clients first.
- `RATE_LIMIT_DB_PATH`: writable quota SQLite database shared by local workers.
  Multiple service instances require a shared quota service.
- `MONITOR_SUMMARY_PATH`: real monitoring-history JSON. Unconfigured monitoring
  reports no invented success rate.

The origin response guard cannot remove an upstream browser challenge.
See `docs/RENDER_DEPLOYMENT.md` and `docs/OPERATIONS_290.md`.
Current evidence lives in `verification/2.9.0/`; older reports/logs are historical.
