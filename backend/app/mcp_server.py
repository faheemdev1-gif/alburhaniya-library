"""
MCP (Model Context Protocol) server for the Burhaniya library.

Provides compact, structured access to the library for MCP clients such as
Claude and ChatGPT.

The recommended retrieval workflow is:

    search_library -> get_page

Search results contain short excerpts. Full text is returned only when the
client deliberately requests a specific page.

SOURCE GRADING
--------------
Every book has a source grade:

- 'أصلي' / primary: authoritative material from the shaykhs.
- 'ثانوي' / secondary: supporting commentary or compilation.

The source classification travels with search results and page responses so
secondary material is not mistakenly attributed directly to a shaykh.

Local run:
    uvicorn app.mcp_server:app --host 0.0.0.0 --port 8001

Deployed:
    Mounted inside app/main.py at /mcp

Claude:
    Add the deployed /mcp URL as a custom Web connector.
"""
from __future__ import annotations

from typing import Literal, Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.core.text_format import format_page
from app.services import library_db as db
from app.services.compact_response import compact_search_response


_RENDER_HOST = "burhaniya-library-backend.onrender.com"

ResponseMode = Literal["compact", "standard"]

_GRADE_REMINDER = "primary=authoritative; secondary=supporting only"


mcp = FastMCP(
    "burhaniya-library",
    instructions=(
        "Arabic Burhaniya library. Always use search_library first, then call "
        "get_page only for the specific results needed. Do not retrieve pages "
        "sequentially unless the question requires adjacent context. Prefer "
        "primary sources; secondary sources are supporting commentary. Never "
        "attribute secondary interpretation directly to a shaykh. Cite the "
        "book and printed page, or seq when no printed page exists. Book b35 "
        "contains multiple speakers: verify the speaker before attribution."
    ),
    stateless_http=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "localhost:*",
            "127.0.0.1:*",
            _RENDER_HOST,
        ],
        allowed_origins=[
            "http://localhost:*",
            "http://127.0.0.1:*",
            f"https://{_RENDER_HOST}",
            "https://claude.ai",
            "https://chatgpt.com",
        ],
    ),
)


@mcp.tool()
def list_books(include_legend: bool = False) -> dict:
    """List books in a compact catalogue, ordered primary-first.

    Args:
        include_legend: Include full source-grade definitions. Leave false
            unless the detailed definitions are specifically required.
    """
    books = [
        {
            "id": book["book_id"],
            "title": book["title"],
            "pages": book["page_count"],
            "source": book["source_code"],
        }
        for book in db.list_books()
    ]

    result = {
        "total": len(books),
        "books": books,
    }

    if include_legend:
        result["grades"] = db.get_grades()

    return result


@mcp.tool()
def get_book(book_id: str) -> dict:
    """Get the metadata and provenance of one book.

    Args:
        book_id: Book ID returned by list_books, such as "b33".
    """
    book = db.get_book(book_id)

    if book is None:
        return {
            "error": f"no book with id '{book_id}'",
        }

    return book


@mcp.tool()
def get_page(
    book_id: str,
    seq: int,
    mode: ResponseMode = "compact",
) -> dict:
    """Read one specific full page.

    Use this only after search_library identifies a relevant result.

    Args:
        book_id: Book ID returned by search_library or list_books.
        seq: Page sequence number, starting at 1.
        mode: "compact" by default. Use "standard" only when legacy navigation
            metadata is required.
    """
    page = db.get_page(book_id, seq)

    if page is None:
        return {
            "error": f"no page {seq} in book '{book_id}'",
        }

    page["text"] = format_page(page["text"])

    if mode == "compact":
        result = {
            "book_id": page["book_id"],
            "book_title": page["book_title"],
            "source": page["source_code"],
            "seq": page["seq"],
            "text": page["text"],
        }

        if page["printed_page"] is not None:
            result["printed_page"] = page["printed_page"]

        if page["has_next"]:
            result["next_seq"] = page["seq"] + 1

        return result

    return page


@mcp.tool()
def get_passage(
    book_id: str,
    seq: int,
    query: str,
    context_chars: int = 800,
) -> dict:
    """Read a bounded passage around a known match instead of a full page."""
    context_chars = max(200, min(context_chars, 2000))
    result = db.get_passage(book_id, seq, query, context_chars)
    if result is None:
        return {"error": f"no page {seq} in book '{book_id}'"}
    return result


@mcp.tool()
def search_library(
    query: Optional[str] = None,
    queries: Optional[list[str]] = None,
    operator: Literal["OR", "AND"] = "OR",
    limit: int = 8,
    offset: int = 0,
    book_ids: Optional[list[str]] = None,
    source_code: Optional[str] = None,
    page_from: Optional[int] = None,
    page_to: Optional[int] = None,
    context_chars: int = 120,
    mode: ResponseMode = "compact",
    diversify_books: bool = True,
    max_per_book: int = 2,
) -> dict:
    """Search exact Arabic words/phrases, with optional OR/AND alternatives.

    Args:
        query: One Arabic word or phrase.
        queries: Optional alternatives in one request. When supplied, this
            takes precedence over query.
        operator: Combine alternatives with OR (default) or AND.
        limit: Number of results. Defaults to 8 and is capped at 20.
        offset: Zero-based pagination offset.
        book_ids: Optional book IDs to search, such as ["b33"].
        source_code: Optional "primary" or "secondary" filter.
        page_from: Optional first page sequence, inclusive.
        page_to: Optional last page sequence, inclusive.
        context_chars: Context on each side of the match. Defaults to 120 and
            is restricted to 40–300.
        mode: "compact" by default. Use "standard" only for compatibility with
            the previous verbose response format.
    """
    limit = max(1, min(limit, 20))
    offset = max(0, offset)
    context_chars = max(40, min(context_chars, 300))

    raw_queries = queries or ([query] if query else [])
    raw_queries = [q for q in raw_queries if q and q.strip()]
    if not raw_queries:
        return {"error": "query or queries cannot be empty"}
    max_per_book = max(1, min(max_per_book, 10))

    if source_code not in (None, "primary", "secondary"):
        return {
            "error": "source_code must be 'primary' or 'secondary'",
        }

    if page_from is not None and page_from < 1:
        return {
            "error": "page_from must be at least 1",
        }

    if page_to is not None and page_to < 1:
        return {
            "error": "page_to must be at least 1",
        }

    if (
        page_from is not None
        and page_to is not None
        and page_from > page_to
    ):
        return {
            "error": "page_from cannot be greater than page_to",
        }

    total_hits = db.count_search(
        raw_queries, operator=operator, book_ids=book_ids,
        source_code=source_code, page_from=page_from, page_to=page_to,
    )

    rows = db.search(
        query=query,
        queries=raw_queries,
        operator=operator,
        book_ids=book_ids,
        source_code=source_code,
        page_from=page_from,
        page_to=page_to,
        limit=limit + 1,
        offset=offset,
        context_chars=context_chars,
        diversify_books=diversify_books,
        max_per_book=max_per_book,
    )

    has_more = len(rows) > limit
    results = rows[:limit]

    if mode == "compact":
        return compact_search_response(
            results,
            limit=limit,
            offset=offset,
            has_more=has_more,
            total_hits=total_hits,
        )

    primary_hits = sum(
        1 for result in results
        if result["source_code"] == "primary"
    )

    return {
        "query": query,
        "queries": raw_queries,
        "operator": operator,
        "book_ids": book_ids,
        "source_code": source_code,
        "returned_count": len(results),
        "total_hits": total_hits,
        "offset": offset,
        "next_offset": offset + limit if has_more else None,
        "primary_hits": primary_hits,
        "secondary_hits": len(results) - primary_hits,
        "provenance": _GRADE_REMINDER,
        "results": results,
    }


app = mcp.streamable_http_app()