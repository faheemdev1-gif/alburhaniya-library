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
_GRADE_REMINDER = (
    "Each result carries source_code: 'primary' (أصلي — the shaykhs' own "
    "words; authoritative on doctrine and meaning) or 'secondary' (ثانوي — "
    "a disciple's or outsider's compilation, commentary, biography, or "
    "administrative text; supporting use only). Never present a secondary "
    "source as the position of the tariqa or attribute its interpretations "
    "to Sidi al-Imam Fakhr al-Din. If a secondary source contradicts a "
    "primary one, state the contradiction plainly rather than reconciling it. "
    "Call list_books for the full legend."
)

mcp = FastMCP(
    "burhaniya-library",
    instructions=(
        "Tools for the Burhaniya Arabic book library.\n\n"
        "- list_books: see every book (id, title, page count, source grade) "
        "plus the source-grade legend. Call this first.\n"
        "- get_book: full metadata for one book by id, including its "
        "provenance note (who compiled it, and any caveat).\n"
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
        "SOURCE GRADING — this matters more than anything else here.\n"
        "Every book is graded 'primary' (أصلي) or 'secondary' (ثانوي), and "
        "the grade is attached to every search hit and every page you read.\n"
        "  primary  = the direct words of Sidi al-Imam Fakhr al-Din (or "
        "another recognised shaykh of the silsila), whether written by his "
        "own hand or transmitted from his lessons and addresses. This is "
        "authoritative and governing on any question of doctrine ('aqida) or "
        "meaning.\n"
        "  secondary = a compilation, commentary, explanation, biography, "
        "lexicon, magazine, or administrative document by a disciple, a "
        "researcher, a commentator, or a scholar from outside the tariqa. "
        "It may quote the shaykhs, but without a verified chain. Use it only "
        "for corroboration, clarification, or as an extra reference.\n"
        "Rules you must follow when answering from this library:\n"
        "  1. Always say which grade a quotation came from.\n"
        "  2. Never attribute a secondary source's interpretation to Sidi "
        "al-Imam Fakhr al-Din or to the tariqa itself.\n"
        "  3. If a secondary source conflicts with a primary one, do NOT "
        "harmonise them — state the conflict openly and leave it for study.\n"
        "  4. Prefer primary sources when both are available. Search results "
        "are already ordered primary-first.\n"
        "  5. Book b35 (كل خطابات المشايخ) is primary but has MULTIPLE "
        "speakers — verify who is speaking in each address before "
        "attributing it.\n\n"
        "Prefer read_book/get_page over repeated broad searches when the "
        "task is 'read/summarize/explain book X' — search_library is for "
        "finding *where* something occurs, not for reading a book "
        "start to finish."
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
def list_books() -> dict:
    """List every book in the library (id, title, page count, source grade),
    together with the source-grade legend that explains how much authority
    each grade carries. Books are ordered primary-first.
    """
    return {
        "grades": db.get_grades(),
        "books": db.list_books(),
    }


@mcp.tool()
def get_book(book_id: str) -> dict:
    """Get metadata for a single book: title, page count, source grade,
    who compiled/authored it, and its provenance note (including any
    caveat about attributing its content).

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

    Returns the page text along with book_title, total_pages, the book's
    source grade, and has_prev/has_next flags so a client can walk
    forward or backward.

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
    """Read a book's pages in reading order, starting at start_seq.

    Returns as many consecutive pages as fit under the per-call cap
    (currently 25 pages / ~40,000 characters, whichever is smaller).
    If the book has more pages after that, `next_seq` is set — call
    read_book again with start_seq=next_seq to continue. When the
    whole book has been read, `next_seq` is null.

    The book's source grade and provenance note are returned once at the
    top level; read them before quoting anything from the pages.

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
    limit: int = 50,
    book_ids: Optional[list[str]] = None,
) -> dict:
    """Search the Arabic library for an exact word or phrase.

    Every result carries the book's source grade (source_code: 'primary'
    or 'secondary'). Results are ordered primary-first. Check the grade
    before quoting: a hit in a secondary source is a disciple's or an
    outsider's words, not the shaykh's.

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
    n_primary = sum(1 for r in results if r["source_code"] == "primary")
    return {
        "query": query,
        "book_ids": book_ids,
        "total": len(results),
        "primary_hits": n_primary,
        "secondary_hits": len(results) - n_primary,
        "provenance": _GRADE_REMINDER,
        "results": results,
    }


app = mcp.streamable_http_app()