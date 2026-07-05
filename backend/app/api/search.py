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


@router.get("/search")
def search_json(
    q: str = Query(..., description="Arabic search query"),
    book_ids: Optional[str] = Query(None, description="Comma-separated book IDs to restrict search"),
    limit: int = Query(2000, ge=1, le=100_000),
):
    """JSON search results — used by the React app."""
    ids = [b.strip() for b in book_ids.split(",")] if book_ids else None
    results = db.search(q, book_ids=ids, limit=limit)
    return {"query": q, "total": len(results), "results": results}


@router.get("/search.html", response_class=HTMLResponse)
def search_html(
    q: str = Query("", description="Arabic search query"),
    limit: int = Query(500, ge=1, le=5000),
):
    """
    Plain, server-rendered search results page — no JavaScript required.
    Built so any tool that can fetch a URL (including an AI's web-fetch
    tool) can search this library directly, the same way it would read
    any other static/server-rendered page.
    """
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
