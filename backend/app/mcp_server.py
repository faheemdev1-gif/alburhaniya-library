"""
MCP (Model Context Protocol) server for the Burhaniya library.

Gives any MCP client (Claude, ChatGPT, etc.) real tools to search AND
read the library, instead of a URL it has to construct and fetch on its
own — an MCP tool call gives structured, validated access directly.

Runs as its own small ASGI app, in the same Docker image as the main
FastAPI app (app/main.py), reusing the same baked-in library.db and the
same functions in app/services/library_db.py — just exposed a different
way. It's mounted inside app/main.py at "/mcp", so streamable_http_path
is set to "/" here (instead of leaving it at its default of "/mcp") to
avoid a doubled "/mcp/mcp" path once mounted.

SOURCE GRADING
--------------
Every book has a source_grade: 'أصلي' (primary — the shaykhs' own words,
authoritative) or 'ثانوي' (secondary — a disciple's/outsider's compilation
or commentary, supporting only). The grade travels with every search hit
and every page, so the model can never quote a commentary as if it were
the Imam. The full legend is returned once by list_books.

Local run:      uvicorn app.mcp_server:app --host 0.0.0.0 --port 8001
Deployed:       mounted inside the main FastAPI app, see app/main.py
Claude side:    add this service's URL + "/mcp" as a custom connector
                (Settings -> Connectors -> Add custom connector).
"""
from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.core.text_format import format_page
from app.services import library_db as db

_RENDER_HOST = "burhaniya-library-backend.onrender.com"

_MAX_PAGES_PER_CALL = 25
_MAX_CHARS_PER_CALL = 40_000

# Short reminder attached to tool results that carry graded material.
# Deliberately terse — the full legend comes from list_books once.
_GRADE_REMINDER = "primary=authoritative; secondary=supporting only"

mcp = FastMCP(
    "burhaniya-library",
    instructions=(
        "Burhaniya Arabic library. Search returns compact excerpts; call "
        "get_page for selected full text and read_book for sequential reading. "
        "Use book/source/page filters and pagination where possible. "
        "Source rule: primary (أصلي) is authoritative shaykh material; "
        "secondary (ثانوي) is supporting commentary or compilation. Identify "
        "the grade when quoting, prefer primary, never attribute secondary "
        "interpretation to the shaykh/tariqa, and state conflicts without "
        "harmonising them. Book b35 has multiple speakers; verify the speaker."
    ),
    stateless_http=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["localhost:*", "127.0.0.1:*", _RENDER_HOST],
        allowed_origins=[
            "http://localhost:*",
            "http://127.0.0.1:*",
            f"https://{_RENDER_HOST}",
        ],
    ),
)


@mcp.tool()
def list_books(include_legend: bool = False) -> dict:
    """List every book in a compact catalogue, ordered primary-first.

    Args:
        include_legend: Include the long source-grade definitions. Defaults
            to false because the server instructions already explain them.
    """
    books = [
        {
            "id": b["book_id"],
            "title": b["title"],
            "pages": b["page_count"],
            "source": b["source_code"],
        }
        for b in db.list_books()
    ]
    result = {"total": len(books), "books": books}
    if include_legend:
        result["grades"] = db.get_grades()
    return result


@mcp.tool()
def get_book(book_id: str) -> dict:
    """Get full metadata and provenance for one book.

    Args:
        book_id: The book's id, as returned by list_books (e.g. "b33").
    """
    book = db.get_book(book_id)
    if book is None:
        return {"error": f"no book with id '{book_id}'"}
    return book


@mcp.tool()
def get_page(book_id: str, seq: int) -> dict:
    """Read one full page by its 1-indexed sequence.

    Args:
        book_id: The book's id, as returned by list_books (e.g. "b33").
        seq: Page sequence number, starting at 1.
    """
    page = db.get_page(book_id, seq)
    if page is None:
        return {"error": f"no page {seq} in book '{book_id}'"}
    # The stored text is flattened: a bayt survives only as `***` between its
    # hemistichs, and consecutive bayts run together on one line. Restore the
    # line breaks so verse is readable as verse.
    page["text"] = format_page(page["text"])
    return page


@mcp.tool()
def read_book(book_id: str, start_seq: int = 1) -> dict:
    """Read consecutive pages; continue from the returned next_seq.

    Args:
        book_id: The book's id, as returned by list_books (e.g. "b33").
        start_seq: Page to start reading from (1-indexed, default 1).
    """
    book = db.get_book(book_id)
    if book is None:
        return {"error": f"no book with id '{book_id}'"}

    total = book["page_count"]
    if start_seq < 1 or start_seq > total:
        return {"error": f"start_seq must be between 1 and {total}"}

    pages = []
    chars = 0
    seq = start_seq
    while seq <= total and len(pages) < _MAX_PAGES_PER_CALL:
        page = db.get_page(book_id, seq)
        if page is None:
            break
        page["text"] = format_page(page.get("text") or "")
        page_chars = len(page["text"])
        if pages and chars + page_chars > _MAX_CHARS_PER_CALL:
            break
        # Grade is stated once at the top level — don't repeat it on all 25 pages.
        for k in ("source_grade", "source_code", "book_title", "total_pages"):
            page.pop(k, None)
        pages.append(page)
        chars += page_chars
        seq += 1

    next_seq = seq if seq <= total else None
    return {
        "book_id": book_id,
        "book_title": book["title"],
        "source_grade": book["source_grade"],
        "source_code": book["source_code"],
        "source_author": book["source_author"],
        "source_note": book["source_note"],
        "total_pages": total,
        "pages": pages,
        "next_seq": next_seq,
    }


@mcp.tool()
def search_library(
    query: str,
    limit: int = 10,
    offset: int = 0,
    book_ids: Optional[list[str]] = None,
    source_code: Optional[str] = None,
    page_from: Optional[int] = None,
    page_to: Optional[int] = None,
    context_chars: int = 160,
) -> dict:
    """Exact Arabic search returning compact, primary-first excerpts.

    Args:
        query: The Arabic word or phrase to search for (e.g. "الحب").
        limit: Results per call (default 10, capped at 50).
        offset: Zero-based result offset for pagination.
        book_ids: Optional list of book ids to restrict the search to
            (e.g. ["b33"]). Get ids from list_books. Omit to search the
            whole library — note that for common words this can return
            many results from other books before reaching the one you
            want, so scoping with book_ids is strongly recommended once
            you know which book you're interested in.
        source_code: Optional "primary" or "secondary" filter.
        page_from: Optional first page sequence (inclusive).
        page_to: Optional last page sequence (inclusive).
        context_chars: Characters of context on each side of the first
            match (default 160, range 40–500).
    """
    limit = max(1, min(limit, 50))
    offset = max(0, offset)
    context_chars = max(40, min(context_chars, 500))
    if source_code not in (None, "primary", "secondary"):
        return {"error": "source_code must be 'primary' or 'secondary'"}
    if page_from is not None and page_from < 1:
        return {"error": "page_from must be at least 1"}
    if page_to is not None and page_to < 1:
        return {"error": "page_to must be at least 1"}
    if page_from is not None and page_to is not None and page_from > page_to:
        return {"error": "page_from cannot be greater than page_to"}

    rows = db.search(
        query,
        book_ids=book_ids,
        source_code=source_code,
        page_from=page_from,
        page_to=page_to,
        limit=limit + 1,
        offset=offset,
        context_chars=context_chars,
    )
    has_more = len(rows) > limit
    results = rows[:limit]
    n_primary = sum(1 for r in results if r["source_code"] == "primary")
    return {
        "query": query,
        "book_ids": book_ids,
        "source_code": source_code,
        "count": len(results),
        "offset": offset,
        "next_offset": offset + limit if has_more else None,
        "primary_hits": n_primary,
        "secondary_hits": len(results) - n_primary,
        "provenance": _GRADE_REMINDER,
        "results": results,
    }


app = mcp.streamable_http_app()
