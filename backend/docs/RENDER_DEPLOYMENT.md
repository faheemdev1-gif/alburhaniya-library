# Render deployment: 2.9.0

## What the screenshot establishes

Render reported no open port and a timeout reaching `/health`. The visible
`asyncio.exceptions.CancelledError` occurred during shutdown. The screenshot
does not include the earlier startup command or first error, so it does not
establish the original cause. The original 2.8.0 application starts locally.

## What this patch changes

- A single persistent entry point, `python scripts/start_server.py`, runs the
  HTTP application on `0.0.0.0` and the port in Render's `PORT` environment
  variable. Without `PORT`, it uses 8000 for local compatibility.
- Invalid ports fail immediately with a readable error.
- The launcher uses the project root and replaces itself with Uvicorn, so the
  server receives termination signals directly.
- Docker uses this launcher. Logs are unbuffered and show backend, corpus and
  MCP initialization stages.

This patch retains the corpus integrity checks. It does not force an unhealthy
application to return HTTP 200. Version 2.9.0 also changes retrieval; original source text remains unchanged. A successful Render deployment remains unverified.

## Existing Render service using Docker

1. Replace the project files in the connected repository with the contents of
   `Al_Burhaniya_Connector_2.9.0`. Keep `Dockerfile`, `app`, `data`, `scripts`,
   requirements files and `tests` together at the configured project root.
2. In Render Settings, check the Root Directory and Dockerfile path. The
   Dockerfile path should identify this release's Dockerfile.
3. Leave **Docker Command** empty so the image's CMD is used. If an override is
   required, set it to `python scripts/start_server.py`.
4. Set **Health Check Path** to `/health`.
5. Keep `ENABLE_LEGACY_MEILISEARCH=false`, `ENABLE_SEMANTIC_SEARCH=false` and
   `ENABLE_LOCAL_SEMANTIC_SEARCH=false` for the included standalone SQLite
   deployment. Remove an unintended `LIBRARY_DB_PATH` override or set it to
   `/app/library.db` for this Dockerfile. Do not point it at an empty mounted
   directory. The index is built into the image; no disk is needed.
6. Deploy the corrected commit. A redeploy or cache-clear operation alone cannot
   correct an old Docker Command override.

The launcher follows Render's existing PORT value, including 8000 or 10000.
Do not set it to the literal text `$PORT`; Render supplies the numeric value.

## If the service uses native Python instead

Use Python 3.11 or 3.12 and the same project root. Set:

**Build Command**

```bash
pip install -r requirements-dev.txt && python scripts/build_index.py && python -m pytest -q && python scripts/independent_corpus_audit.py library.db
```

**Start Command**

```bash
python scripts/start_server.py
```

**Health Check Path:** `/health`

Leave `LIBRARY_DB_PATH` unset for the default project-root index. Verification
scripts are finite checks and must not be used as the Start Command. The start
step does not build the database, run tests or launch optional search services.

## Confirm the result

Startup logs should show `Starting library HTTP service on 0.0.0.0:...`, three
startup stages, `Library startup complete` and `Uvicorn running`. A request to
`/health` should return HTTP 200 with `server_version: 2.9.0` and a healthy
corpus contract. MCP remains at `/mcp/`.

After deployment, run the five-tool check:

```bash
python scripts/production_mcp_regression.py --endpoint https://burhaniya-library-backend.onrender.com/mcp/
```

If deployment still fails, capture the logs from the start of runtime through
the **first** error, plus Render's Start Command or Docker Command and Root
Directory. The final port-timeout/shutdown lines alone cannot distinguish an
incorrect command, startup exception, resource termination or configuration
mismatch. Remove secret values before sharing logs or settings.

Reference: https://render.com/docs/web-services#port-binding
