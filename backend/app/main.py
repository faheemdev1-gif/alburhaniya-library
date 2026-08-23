import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.core.config import get_settings
from app.core.html_templates import page_shell, nav_bar
from app.mcp_contract import SERVER_VERSION, contract_metadata, validate_registered_tools
from app.api import books, search, files
from app.mcp_server import mcp

logger = logging.getLogger(__name__)
s = get_settings()


def _init_search_backend():
    """Same startup logic as before, just factored out so the lifespan
    function below can call it before yielding."""
    if s.enable_legacy_meilisearch:
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run the same startup checks as before.
    _init_search_backend()
    # FastMCP's streamable-HTTP transport needs its session manager's task
    # group started as part of the ASGI lifespan — app.mount() alone does
    # NOT forward a sub-app's lifespan, so without this the MCP endpoint
    # throws "Task group is not initialized. Make sure to use run()."
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="Arabic Library Search",
    description="Exact-word search over the Burhaniya Arabic book collection",
    version=SERVER_VERSION,
    lifespan=lifespan,
)

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

app.mount("/mcp", mcp.streamable_http_app())


@app.get("/health")
def health():
    tools = validate_registered_tools(mcp)
    return {"status": "ok", **contract_metadata(tools)}


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
