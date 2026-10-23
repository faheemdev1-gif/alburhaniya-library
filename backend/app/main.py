import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app.core.config import get_settings
from app.core.resilience import new_request_id, safe_error_payload
from app.core.html_templates import page_shell, nav_bar
from app.mcp_contract import SERVER_VERSION, contract_metadata, validate_registered_tools
from app.api import books, search, files
from app.mcp_server import mcp
from app.services.corpus_contract import corpus_contract_snapshot

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
    from app.services.concept_links import prepare_patterns
    prepare_patterns()


@asynccontextmanager
async def lifespan(app: FastAPI):
    started = time.monotonic()
    logger.info("Startup stage 1/3: verifying search backend")
    _init_search_backend()
    logger.info("Startup stage 2/3: validating corpus contract")
    corpus = corpus_contract_snapshot()
    if corpus["status"] != "ok":
        raise RuntimeError(f"BROKEN CORPUS CONTRACT: {corpus}")
    # FastMCP's streamable-HTTP transport needs its session manager's task
    # group started as part of the ASGI lifespan — app.mount() alone does
    # NOT forward a sub-app's lifespan, so without this the MCP endpoint
    # throws "Task group is not initialized. Make sure to use run()."
    logger.info("Startup stage 3/3: starting MCP session manager")
    async with mcp.session_manager.run():
        logger.info("Library startup complete in %.3fs", time.monotonic() - started)
        yield


app = FastAPI(
    title="Arabic Library Search",
    description="Exact-word search over the Burhaniya Arabic book collection",
    version=SERVER_VERSION,
    lifespan=lifespan,
)


@app.middleware("http")
async def api_safe_failures(request: Request, call_next):
    """Attach a correlation id and keep unexpected errors concise and JSON-safe."""
    request_id = new_request_id(request.headers.get("x-request-id"))
    started = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "unhandled request failure path=%s request_id=%s",
            request.url.path, request_id,
        )
        response = JSONResponse(
            safe_error_payload(
                "temporary_unavailable",
                "The library is temporarily unavailable. Retry the request shortly.",
                retryable=True,
                retry_after_seconds=1,
            ),
            status_code=503,
            headers={"Retry-After": "1", "Cache-Control": "no-store"},
        )
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request complete method=%s path=%s status=%s elapsed_ms=%d request_id=%s",
        request.method, request.url.path, response.status_code,
        int((time.monotonic() - started) * 1000), request_id,
    )
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in s.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.core.machine_http import MachineHTTP
app.add_middleware(MachineHTTP)

@app.get("/schemas/tools.json")
def tool_schemas():
    return {"contract":contract_metadata(),"tools":[{"name":t.name,"inputSchema":t.parameters} for t in mcp._tool_manager.list_tools()]}

app.include_router(books.router)
app.include_router(search.router)
app.include_router(files.router)

app.mount("/mcp", mcp.streamable_http_app())


@app.get("/health")
def health():
    tools = validate_registered_tools(mcp)
    corpus = corpus_contract_snapshot()
    payload = {
        "status": "ok" if corpus["status"] == "ok" else "broken",
        **contract_metadata(tools),
        "corpus_contract": corpus,
    }
    if corpus["status"] != "ok":
        return JSONResponse(payload, status_code=503)
    return payload


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
