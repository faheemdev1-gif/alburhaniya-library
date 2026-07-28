from __future__ import annotations
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse
from typing import Optional
from html import escape as _esc

from app.core.config import get_settings
from app.core.html_templates import page_shell, nav_bar, search_form
from app.services import library_db as db

router = APIRouter(tags=["search"])


def _page_url(s, book_id: str, seq: int) -> str:
    if s.static_site_base_url:
        return f"{s.static_site_base_url.rstrip('/')}/books/{book_id}/p{seq:04d}.html"
    return f"/read/{book_id}/{seq}"


def _render_results_html(q: str, limit: int) -> str:
    s = get_settings()
    crumbs = nav_bar([("المكتبة", "/books.html")])

    if not q.strip():
        body = crumbs + "<h1>البحث في المكتبة</h1>" + search_form(q)
        return page_shell("البحث في المكتبة", body)

    results = db.search(q, limit=limit)
    body_parts = [
        crumbs,
        f"<h1>نتائج البحث عن: {_esc(q)}</h1>",
        search_form(q),
        f'<p class="meta">عدد الصفحات التي وردت فيها الكلمة: {len(results)}</p>',
    ]
    for r in results:
        url = _page_url(s, r["book_id"], r["seq"])
        body_parts.append(
            '<div class="result">'
            f'<h3><a href="{url}">{_esc(r["book_title"])} — {_esc(r["page_label"])}</a></h3>'
            f'<p class="occ">عدد مرات الورود في هذه الصفحة: {r["occurrences"]}</p>'
            f'<p class="snippet">{r["snippet"]}</p>'
            "</div>"
        )
    return page_shell(f"نتائج البحث: {q}", "\n".join(body_parts), description=f"نتائج البحث عن {q}")


# ── Query-string endpoints (used by the React app; also fine for humans) ──

@router.get("/search")
def search_json(
    q: str = Query(..., description="Arabic search query"),
    book_ids: Optional[str] = Query(None, description="Comma-separated book IDs to restrict search"),
    limit: int = Query(2000, ge=1, le=100_000),
):
    """JSON search results — used by the React app."""
    ids = [b.strip() for b in book_ids.split(",")] if book_ids else None
    results = db.search(q, book_ids=ids, limit=limit, include_full_text=True)
    return {"query": q, "total": len(results), "results": results}


@router.get("/search.html", response_class=HTMLResponse)
def search_html(
    q: str = Query("", description="Arabic search query"),
    limit: int = Query(500, ge=1, le=5000),
):
    """Plain, server-rendered search results page (query-string form)."""
    return _render_results_html(q, limit)


# ── Path-based endpoints (word IS the URL — fetchable without any ?query) ──
# Exists specifically so an AI's URL-fetch tool (which may refuse a
# self-constructed ?q=... query string) can search this library on its
# own, by building a plain path instead: /search/كلمة or /api/search/كلمة.

@router.get("/search/{query}", response_class=HTMLResponse)
def search_html_path(query: str, limit: int = Query(500, ge=1, le=5000)):
    """Same as /search.html, but the word is a URL path segment, e.g.
    GET /search/قلب — no query string involved at all."""
    return _render_results_html(query, limit)


@router.get("/api/search/{query}")
def search_json_path(query: str, limit: int = Query(2000, ge=1, le=100_000)):
    """Same as /search, but the word is a URL path segment, e.g.
    GET /api/search/قلب — no query string involved at all."""
    results = db.search(query, limit=limit, include_full_text=True)
    return {"query": query, "total": len(results), "results": results}
