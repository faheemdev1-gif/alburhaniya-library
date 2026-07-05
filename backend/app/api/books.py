from __future__ import annotations
from html import escape as _esc
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.core.config import get_settings
from app.core.html_templates import page_shell, nav_bar
from app.services import library_db as db

router = APIRouter(tags=["books"])


# ── JSON API (used by the React app) ─────────────────────────────────────

@router.get("/books/")
def list_books():
    return db.list_books()


@router.get("/books/{book_id}/page/{seq}")
def get_page_text(book_id: str, seq: int):
    """Return the text of a specific book page for the app's text viewer."""
    page = db.get_page(book_id, seq)
    if not page:
        raise HTTPException(404, "Page not found")
    return page


# ── Legacy ingestion endpoints (Meilisearch-based pipeline) ─────────────
# Kept for anyone who re-enables the docker-compose Meilisearch/Qdrant
# stack; not used by the default SQLite-FTS5 deployment.

@router.post("/books/ingest-all")
def ingest_all():
    s = get_settings()
    if not s.enable_legacy_meilisearch:
        raise HTTPException(
            501,
            "Legacy ingestion is disabled in this deployment. This library "
            "is served from a pre-built library.db (see scripts/build_index.py). "
            "Set ENABLE_LEGACY_MEILISEARCH=true and run the Meilisearch/Qdrant "
            "docker-compose stack to use the old ingestion pipeline instead.",
        )
    from app.services.ingestion import ingest_directory
    return {"message": "started", "results": ingest_directory(s.books_dir)}


@router.post("/books/upload")
def upload_book():
    raise HTTPException(
        501,
        "Uploading new books at runtime isn't available in this deployment. "
        "This library is served from a pre-built library.db — add a new .htm "
        "file to backend/data/raw_htm, update mapping.json, and redeploy "
        "(library.db rebuilds automatically at Docker build time).",
    )


@router.delete("/books/{book_id}")
def delete_book(book_id: str):
    raise HTTPException(
        501,
        "Deleting books at runtime isn't available in this deployment. "
        "Remove the book's .htm file from backend/data/raw_htm and its "
        "entry from mapping.json, then redeploy.",
    )


# ── Server-rendered HTML pages (no JS needed to read) ────────────────────

@router.get("/books.html", response_class=HTMLResponse)
def books_index_html():
    books = db.list_books()
    items = "\n".join(
        f'<div class="result"><h3><a href="/read/{b["book_id"]}/1">{_esc(b["title"])}</a> '
        f'<span class="occ">({b["page_count"]} صفحة)</span></h3></div>'
        for b in books
    )
    body = (
        nav_bar([("البحث", "/search.html")])
        + f"<h1>المكتبة البرهانية</h1><p class='meta'>{len(books)} كتاباً</p>"
        + items
    )
    return page_shell("المكتبة البرهانية", body)


@router.get("/read/{book_id}/{seq}", response_class=HTMLResponse)
def read_page_html(book_id: str, seq: int):
    page = db.get_page(book_id, seq)
    if not page:
        raise HTTPException(404, "Page not found")

    label = f"الصفحة {page['printed_page']}" if page["printed_page"] else f"المقطع {page['seq']}"
    nav_links = [("فهرس المكتبة", "/books.html"), ("بحث", "/search.html")]
    if page["has_prev"]:
        nav_links.insert(0, ("السابق ←", f"/read/{book_id}/{seq-1}"))
    if page["has_next"]:
        nav_links.append(("→ التالي", f"/read/{book_id}/{seq+1}"))

    body = (
        nav_bar(nav_links)
        + f"<h1>{_esc(page['book_title'])}</h1>"
        + f"<h2>{_esc(label)}</h2>"
        + '<article class="page-text">'
        + "\n".join(f"<p>{_esc(p)}</p>" for p in page["text"].split("\n\n"))
        + "</article>"
        + nav_bar(nav_links)
    )
    return page_shell(f"{page['book_title']} — {label}", body, description=f"{page['book_title']} — {label}")
