# المكتبة البرهانية — Arabic Library (search + static reading + interactive app)

This project now has **two complementary deployments** built from the same
43 shamela.ws-exported books:

1. **This backend** (`backend/`) — exact-word search + server-rendered HTML
   pages, deployed as one lean, free container (see "Deploying the backend"
   below). This is what makes the library **searchable and readable by an
   AI or any plain HTTP client** — no JavaScript required.
2. **A static site** (built separately, see the `burhaniya-static-library`
   deliverable) — every page pre-rendered as its own static HTML file, for
   hosting on Vercel. Cross-linked with this backend via `STATIC_SITE_BASE_URL`.
3. **The React app** (`frontend/`) — the original interactive search UI
   with the in-browser page viewer, for human use. Talks to this backend's
   JSON endpoints (`/search`, `/books/...`).

## How search works now

```
data/raw_htm/*.htm  (43 shamela.ws exports, windows-1256)
        |
        v
scripts/build_index.py   -- runs once, at Docker BUILD time
        |                    (parses pages, normalises Arabic, builds FTS5 index)
        v
   library.db  (SQLite + FTS5)   <- baked into the image, no persistent disk needed
        |
        v
   FastAPI backend
        +-- GET /search           JSON  (used by the React app)
        +-- GET /search.html      plain server-rendered HTML results page
        +-- GET /books.html       plain server-rendered library index
        +-- GET /read/{id}/{seq}  plain server-rendered single page
```

Every "page" in the database is a real source page (the `(الجزء/الصفحة)`
markers already in the shamela exports), so search results are already
one-card-per-page -- no chunk-merging needed. Semantic/embedding search is
still in the codebase (`app/services/hybrid_search.py`) but OFF by default;
flip `ENABLE_SEMANTIC_SEARCH=true` and run the legacy Meilisearch/Qdrant
compose stack to bring it back.

## Deploying the backend (Render, free)

1. Push this repo to GitHub.
2. In Render: **New -> Blueprint**, point it at the repo -- `render.yaml` at
   the repo root configures everything (free plan, Dockerfile in `backend/`).
3. Once deployed you get a URL like `https://burhaniya-library-backend.onrender.com`.
   Try:
   - `https://.../search.html?q=التوحيد` -- server-rendered search results
   - `https://.../books.html` -- full library index
   - `https://.../health` -- should return `{"status":"ok"}`
4. **Free-tier note:** the service spins down after 15 minutes idle; the
   first request after that takes up to ~30-60s to wake up.
5. If/when you deploy the companion static site to Vercel, set the
   `STATIC_SITE_BASE_URL` env var on Render to that site's URL -- search
   results will then link to the static pages instead of this backend's
   own `/read/...` pages.

## Local development

```bash
docker compose up -d --build
# backend:  http://localhost:8000
# frontend: http://localhost:3000
```

## Adding or updating books

1. Add the new `.htm` file to `backend/data/raw_htm/`, add its title to
   `backend/data/mapping.json`.
2. Redeploy -- `library.db` rebuilds automatically from source at Docker
   build time (see `backend/Dockerfile`).

## Legacy / optional

- `docker-compose.legacy-meilisearch.yml` -- the original Meilisearch +
  Qdrant + GPU-embeddings hybrid-search stack, if you want semantic search
  back and are running somewhere with the resources for it.
- `docker-compose.gpu.yml` -- GPU override for that legacy stack.
- `books/` -- the original 41 plain-.txt books from before the shamela.ws
  `.htm` exports became the canonical source. Not used by the current
  SQLite-FTS5 pipeline.
- `scripts/convert_to_pdf.sh` -- unrelated utility kept from earlier work.
