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

## The React app (`frontend/`)

Two screens, one search field.

- **Library** — every book grouped by source grade. The header search field
  is scoped to the whole library; results list one card per matching page.
- **Reader** — opening a book (from the index, or from a search result) keeps
  the same field in the same place but narrows its scope to that book. Hits
  appear as a jump-list beside the page and stay highlighted as you read. A
  link under the field widens the same query back out to the whole library.

`/` focuses the search field, `←` / `→` turn pages, `Esc` clears the search.

### How pages are formatted

The shamela exports flatten each page into running text: poetry survives only
as a `***` between the two hemistichs of a bayt, and consecutive bayts run
together on one line with the commentary flowing straight into them. Across
the corpus that is 8,849 separators on 2,326 pages, with 1,033 paragraphs
holding more than one bayt inline.

`src/utils/formatText.js` recovers the structure. Splitting on `***` is not
enough — the hard part is knowing where the verse starts and stops. The signal
it uses is vocalisation: poetry here is fully voweled (median diacritic-to-
letter ratio 0.75) while the commentary around it is bare (median 0.00). So it
classifies each word, grows a verse span outward from every `***`, and stops
where the vowels stop. Inside a span the `***` marks exact hemistich
boundaries; where two bayts run together it cuts on the bayt number
(`419-`, `3 ق 1:`) when there is one, and otherwise on metre, since hemistichs
within a qasida are near-constant in length.

It returns typed blocks — `bayt`, `para`, `heading`, `quote`, `divider`,
`folio` — which `components/PageText.jsx` renders: couplets as couplets, with
the two hemistichs meeting at a rosette. `src/utils/arabic.js` adds the inline
layer: Qur'anic citations, quoted hadith, and search highlighting that matches
the way the backend matches (diacritics skippable, alef/ya/ta-marbuta
interchangeable).

Over all 7,450 pages this yields 8,213 bayts with no errors, in about 1.5s —
roughly 0.2ms per page, so it runs per-page at render time.

**This lives in the frontend only.** The server-rendered `/read/...` pages and
the MCP output still emit the raw flattened text; porting `formatText.js` to
`backend/app/core/` would give AI clients the same structure.

## Deploying (Render, free)

`render.yaml` at the repo root defines all three services, so **New → Blueprint**
in Render sets up everything from one file:

| service | type | what it is |
|---|---|---|
| `burhaniya-library-frontend` | static site | the React reader, on Render's CDN |
| `burhaniya-library-backend`  | docker | FastAPI + SQLite FTS5, JSON + server-rendered HTML |
| `burhaniya-library-mcp`      | docker | the same image, started as the MCP server |

The frontend rewrites `/api/*` onto the backend's public URL, so the browser
stays on one origin — no CORS, and the backend URL never lands in the bundle.
**If you rename the backend service, update that rewrite destination in
`render.yaml`**, or every API call will 404.

Prefer to host the frontend elsewhere (Vercel, Netlify, Cloudflare Pages)?
Build with `VITE_API_BASE` set to the backend's URL and it will call the
backend directly instead; the backend already sends
`Access-Control-Allow-Origin: *`.

Once deployed, check:

- `https://<backend>/health` → `{"status":"ok"}`
- `https://<backend>/books.html` → the full library index
- `https://<backend>/search.html?q=التوحيد` → server-rendered results

**Free-tier note:** the two docker services spin down after 15 minutes idle,
and the next request takes 30–60s to wake them. The static frontend never
sleeps, so the page loads instantly while the first search sits waiting. If
that matters, put the backend on a paid instance or ping `/health` on a
schedule to keep it warm.

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
