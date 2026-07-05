import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.core.config import get_settings
from app.core.html_templates import page_shell, nav_bar
from app.api import books, search, files

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Arabic Library Search",
    description="Exact-word search over the Burhaniya Arabic book collection",
    version="2.0.0",
)

s = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in s.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(books.router)
app.include_router(search.router)
app.include_router(files.router)


@app.on_event("startup")
async def startup():
    if s.enable_legacy_meilisearch:
        import time
        from app.services.keyword_search import ensure_index
        for attempt in range(1, 6):
            try:
                ensure_index()
                if s.enable_semantic_search:
                    from app.services.vector_search import ensure_collection
                    ensure_collection()
                return
            except Exception as e:
                if attempt == 5:
                    raise
                wait = attempt * 3
                logger.warning("Startup attempt %d/5 failed (%s) — retrying in %ds…", attempt, e, wait)
                time.sleep(wait)
        return

    # Default path: SQLite FTS5, baked into the image — just verify it exists.
    if not os.path.exists(s.library_db_path):
        raise RuntimeError(
            f"library.db not found at {s.library_db_path!r}. "
            "Run `python scripts/build_index.py` (this happens automatically "
            "during `docker build`, see Dockerfile)."
        )
    logger.info("library.db found at %s ✓", s.library_db_path)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home():
    body = (
        nav_bar([("فهرس الكتب", "/books.html"), ("البحث", "/search.html")])
        + "<h1>المكتبة البرهانية — بحث ذكي</h1>"
        + "<p class='meta'>مكتبة نصية قابلة للبحث والقراءة مباشرة، بدون جافاسكربت.</p>"
        + "<ul><li><a href='/books.html'>فهرس كل الكتب</a></li>"
        + "<li><a href='/search.html'>صفحة البحث</a></li></ul>"
    )
    return page_shell("المكتبة البرهانية", body)
