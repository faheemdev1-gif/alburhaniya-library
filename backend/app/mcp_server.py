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

Local run:      uvicorn app.mcp_server:app --host 0.0.0.0 --port 8001
Deployed:       mounted inside the main FastAPI app, see app/main.py
Claude side:    add this service's URL + "/mcp" as a custom connector
                (Settings -> Connectors -> Add custom connector).
"""
from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.services import library_db as db

# FastMCP's DNS-rebinding protection only allows localhost/127.0.0.1 by
# default (because no `host` is passed at construction time). Deployed
# behind Render + Cloudflare, real requests arrive with a Host header of
# our public domain, which gets rejected as "421 Invalid Host header"
# unless we explicitly allow it here. Add any other domain you deploy to
# (e.g. a custom domain) to allowed_hosts/allowed_origins as needed.
_RENDER_HOST = "burhaniya-library-backend.onrender.com"

# Cap on how much page-text a single read_book call returns, so large
# books (the 659-page administrative manual, etc.) don't blow out a
# single tool result on any client. The model pages through via
# next_seq instead.
_MAX_PAGES_PER_CALL = 25
_MAX_CHARS_PER_CALL = 40_000

mcp = FastMCP(
    "burhaniya-library",
    instructions=(
        "Tools for the Burhaniya Arabic book library.\n\n"
        "- list_books: see every book (id, title, page count).\n"
        "- get_book: metadata for one book by id.\n"
        "- get_page: read a single page of a book by its sequence number.\n"
        "- read_book: read a book's pages in order, starting at start_seq. "
        "Returns up to a capped number of pages per call plus a next_seq "
        "cursor — call again with start_seq=next_seq to continue until "
        "next_seq is null. For short books (a few dozen pages) one call "
        "usually returns the whole thing.\n"
        "- search_library: exact word/phrase search across the whole "
        "library, or restrict to one or more books with book_ids for a "
        "much more precise lookup once you know which book you care "
        "about (get the id from list_books first).\n\n"
        "Prefer read_book/get_page over repeated broad searches when the "
        "task is 'read/summarize/explain book X' — search_library is for "
        "finding *where* something occurs, not for reading a book "
        "start to finish."
    ),
    stateless_http=True,
    # Serve at root internally — app/main.py mounts this whole app at
    # "/mcp", so leaving the default "/mcp" here would produce "/mcp/mcp".
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
def list_books() -> dict:
    """List every book in the library (id, title, page count)."""
    return {"books": db.list_books()}


@mcp.tool()
def get_book(book_id: str) -> dict:
    """Get metadata (id, title, page count) for a single book.

    Args:
        book_id: The book's id, as returned by list_books (e.g. "b33").
    """
    book = db.get_book(book_id)
    if book is None:
        return {"error": f"no book with id '{book_id}'"}
    return book


@mcp.tool()
def get_page(book_id: str, seq: int) -> dict:
    """Read a single page of a book by its sequence number (1-indexed).

    Returns the page text along with book_title, total_pages, and
    has_prev/has_next flags so a client can walk forward or backward.

    Args:
        book_id: The book's id, as returned by list_books (e.g. "b33").
        seq: Page sequence number, starting at 1.
    """
    page = db.get_page(book_id, seq)
    if page is None:
        return {"error": f"no page {seq} in book '{book_id}'"}
    return page


@mcp.tool()
def read_book(book_id: str, start_seq: int = 1) -> dict:
    """Read a book's pages in reading order, starting at start_seq.

    Returns as many consecutive pages as fit under the per-call cap
    (currently 25 pages / ~40,000 characters, whichever is smaller).
    If the book has more pages after that, `next_seq` is set — call
    read_book again with start_seq=next_seq to continue. When the
    whole book has been read, `next_seq` is null.

    For short books (roughly under 25 pages) this typically returns
    the entire book in a single call.

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
        page_chars = len(page.get("text") or "")
        if pages and chars + page_chars > _MAX_CHARS_PER_CALL:
            break
        pages.append(page)
        chars += page_chars
        seq += 1

    next_seq = seq if seq <= total else None
    return {
        "book_id": book_id,
        "book_title": book["title"],
        "total_pages": total,
        "pages": pages,
        "next_seq": next_seq,
    }


@mcp.tool()
def search_library(
    query: str,
    limit: int = 50,
    book_ids: Optional[list[str]] = None,
) -> dict:
    """Search the Arabic library for an exact word or phrase.

    Args:
        query: The Arabic word or phrase to search for (e.g. "الحب").
        limit: Maximum number of matching pages to return (default 50,
            capped at 500).
        book_ids: Optional list of book ids to restrict the search to
            (e.g. ["b33"]). Get ids from list_books. Omit to search the
            whole library — note that for common words this can return
            many results from other books before reaching the one you
            want, so scoping with book_ids is strongly recommended once
            you know which book you're interested in.
    """
    limit = max(1, min(limit, 500))
    results = db.search(query, book_ids=book_ids, limit=limit)
    return {"query": query, "book_ids": book_ids, "total": len(results), "results": results}


# Streamable-HTTP ASGI app. When run standalone (uvicorn app.mcp_server:app)
# this serves at "/" per streamable_http_path above. When mounted inside
# app/main.py at "/mcp", the combined external path is a clean "/mcp".
app = mcp.streamable_http_app()