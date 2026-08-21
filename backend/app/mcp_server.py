"""
MCP (Model Context Protocol) server for the Burhaniya library.

Provides compact, structured access to the library for MCP clients such as
Claude and ChatGPT.

The recommended retrieval workflow is:

    search_library -> get_passage -> get_page (only when necessary)

Search results contain short excerpts and stable match ids. Focused passages
are the normal second step; full text is returned only when the client
deliberately requests a specific page.

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

from typing import Any, Literal, Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.core.text_format import format_page
from app.services import library_db as db
from app.services.compact_response import compact_search_response


_RENDER_HOST = "burhaniya-library-backend.onrender.com"

ResponseMode = Literal["compact", "ultra_compact"]

_GRADE_REMINDER = "primary=authoritative; secondary=supporting only"


mcp = FastMCP(
    "burhaniya-library",
    instructions=(
        "Arabic Burhaniya library. Always use search_library first, then call "
        "get_passage with a returned match_id. Use get_page only when the whole "
        "page is genuinely needed. Do not retrieve pages "
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


@mcp.tool(structured_output=True)
def list_books(include_legend: bool = False) -> dict[str, Any]:
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
            "tier": book["source_tier"],
        }
        for book in db.list_books()
    ]

    result = {
        "total": len(books),
        "books": books,
    }

    if include_legend:
        result["grades"] = db.get_grades()
        result["tiers"] = db.get_tiers()

    return result


@mcp.tool(structured_output=True)
def get_book(book_id: str) -> dict[str, Any]:
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


@mcp.tool(structured_output=True)
def get_page(
    book_id: str,
    seq: int,
    mode: ResponseMode = "compact",
    max_chars: int = 6000,
) -> dict[str, Any]:
    """Read one specific full page.

    Use this only after search_library identifies a relevant result.

    Args:
        book_id: Book ID returned by search_library or list_books.
        seq: Page sequence number, starting at 1.
        mode: Response shape. Supported values are "compact" and
            "ultra_compact" only.
    """
    page = db.get_page(book_id, seq)

    if page is None:
        return {
            "error": f"no page {seq} in book '{book_id}'",
        }

    page["text"] = format_page(page["text"])
    max_chars = max(1000, min(max_chars, 20000))
    full_chars = len(page["text"])
    oversized = full_chars > max_chars
    if oversized:
        page["text"] = page["text"][:max_chars] + "…"

    if mode in ("compact", "ultra_compact"):
        result = {
            "book_id": page["book_id"],
            "book_title": page["book_title"],
            "source": page["source_code"],
            "tier": page["source_tier"],
            "seq": page["seq"],
            "text": page["text"],
        }

        if page["printed_page"] is not None:
            result["printed_page"] = page["printed_page"]
        elif page.get("citation_label"):
            result["citation_label"] = page["citation_label"]

        if page["has_next"]:
            result["next_seq"] = page["seq"] + 1
        if oversized:
            result["truncated"] = True
            result["full_chars"] = full_chars
            result["hint"] = "Use get_passage for focused context or raise max_chars deliberately."

        return result

    return page


@mcp.tool(structured_output=True)
def get_passage(
    match_id: Optional[str] = None,
    match_ids: Optional[list[str]] = None,
    context_chars: int = 600,
    query: Optional[str] = None,
) -> dict[str, Any]:
    """Read one or several bounded passages returned by search_library."""
    context_chars = max(200, min(context_chars, 2000))
    if match_ids:
        results = []
        for item in match_ids[:20]:
            match = db._MATCH_ID_RE.fullmatch(item or "")
            result = (db.get_passage(match.group(1), int(match.group(2)), query=query,
                      context_chars=context_chars, match_start=int(match.group(3)))
                      if match else None)
            results.append(result or {"error": f"invalid or unknown match_id '{item}'"})
        return {"returned_count": len(results), "results": results}
    if not match_id:
        return {"error": "match_id or match_ids is required"}
    if query:
        match = db._MATCH_ID_RE.fullmatch(match_id or "")
        result = (db.get_passage(match.group(1), int(match.group(2)), query=query,
                                 context_chars=context_chars,
                                 match_start=int(match.group(3))) if match else None)
    else:
        result = db.get_passage_by_match_id(match_id, context_chars)
    if result is None:
        return {"error": f"invalid or unknown match_id '{match_id}'"}
    return result


@mcp.tool(structured_output=True)
def search_library(
    query: Optional[str] = None,
    queries: Optional[list[str]] = None,
    operator: Literal["OR", "AND"] = "OR",
    limit: int = 8,
    offset: int = 0,
    book_ids: Optional[list[str]] = None,
    book_scope: Optional[str] = None,
    source_code: Optional[str] = None,
    page_from: Optional[int] = None,
    page_to: Optional[int] = None,
    context_chars: int = 60,
    mode: ResponseMode = "compact",
    match_mode: Literal["auto", "exact", "terms", "hybrid", "lexeme"] = "auto",
    search_mode: Optional[Literal["exact_phrase", "all_words", "any_word", "lexeme"]] = None,
    ranking: Literal["relevance", "primary_first", "chronological", "book_order"] = "primary_first",
    diversify_books: bool = True,
    max_per_book: int = 2,
    include_counts: bool = False,
    min_score: float = 0.0,
    qasida_number: Optional[int] = None,
    expand_top: int = 0,
    expand_chars: int = 600,
) -> dict[str, Any]:
    """Search exact Arabic words/phrases, with optional OR/AND alternatives.

    Args:
        query: One Arabic word or phrase.
        queries: Optional alternatives in one request. When supplied, this
            takes precedence over query.
        operator: Combine alternatives with OR (default) or AND.
        limit: Number of results. Defaults to 8 and is capped at 20.
        offset: Zero-based pagination offset.
        book_ids: Optional book IDs to search, such as ["b33"].
        book_scope: Optional title/series fragment, such as "شرح شراب الوصل".
        source_code: Optional "primary" or "secondary" filter.
        page_from: Optional first page sequence, inclusive.
        page_to: Optional last page sequence, inclusive.
        context_chars: Context on each side of the match. Defaults to 60 and
            is restricted to 40–300.
        mode: compact or ultra_compact.
        match_mode: auto, exact, terms, hybrid, or lexeme. When a local
            semantic index is present, auto unions exact, terms, lexeme and
            semantic candidates and reranks them. Otherwise it falls back to
            exact, terms, then lexical hybrid. Every hit declares match_type. Lexeme
            accepts one Arabic word per query and expands common proclitics,
            suffixes, and weak-final ي/ا forms for recall-oriented census work.
            Every hit also includes a normalized relevance score from 0 to 1;
            higher scores indicate stronger relevance within that result set.
        ranking: relevance, primary_first, chronological, or book_order.
    """
    limit = max(1, min(limit, 20))
    offset = max(0, offset)
    context_chars = max(40, min(context_chars, 300))

    raw_queries = queries or ([query] if query else [])
    raw_queries = [q for q in raw_queries if q and q.strip()]
    if not raw_queries:
        return {"error": "query or queries cannot be empty"}
    max_per_book = max(1, min(max_per_book, 10))
    min_score = max(0.0, min(min_score, 1.0))

    if book_scope:
        scoped_ids = db.resolve_book_scope(book_scope)
        if not scoped_ids:
            return {"error": f"no books match scope '{book_scope}'"}
        book_ids = sorted(set(book_ids or scoped_ids) & set(scoped_ids)) if book_ids else scoped_ids
        if not book_ids:
            return {"error": "book_ids and book_scope do not overlap"}

    resolved_search_mode = search_mode or {
        "auto": "exact_phrase",
        "exact": "exact_phrase", "terms": "all_words", "lexeme": "lexeme",
        "hybrid": "all_words",
    }[match_mode]

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

    total_hits = stats = None
    if include_counts:
        total_hits = db.count_search(
            raw_queries, operator=operator, book_ids=book_ids,
            source_code=source_code, page_from=page_from, page_to=page_to,
            search_mode=resolved_search_mode,
        )
        stats = db.search_stats(
            raw_queries, operator=operator, book_ids=book_ids,
            source_code=source_code, page_from=page_from, page_to=page_to,
            search_mode=resolved_search_mode,
        )

    effective_match_mode = match_mode
    if match_mode == "auto":
        from app.services import semantic_search as semantic
        if semantic.semantic_available():
            rows = semantic.auto_search(
                query=query, queries=raw_queries, operator=operator,
                search_mode=resolved_search_mode, ranking=ranking,
                book_ids=book_ids, source_code=source_code,
                page_from=page_from, page_to=page_to, limit=limit + 1,
                offset=offset, context_chars=context_chars,
                diversify_books=diversify_books, max_per_book=max_per_book,
                qasida_number=qasida_number, min_score=min_score,
            )
        else:
            cascade = (("exact", "exact_phrase", db.search),
                       ("terms", "all_words", db.search),
                       ("hybrid", "all_words", db.hybrid_search))
            rows = []
            for effective_match_mode, resolved_search_mode, candidate_fn in cascade:
                probe = dict(query=query, queries=raw_queries, operator=operator,
                             search_mode=resolved_search_mode, ranking=ranking,
                             book_ids=book_ids, source_code=source_code,
                             page_from=page_from, page_to=page_to, limit=limit + 1,
                             offset=offset, context_chars=context_chars,
                             diversify_books=diversify_books, max_per_book=max_per_book,
                             qasida_number=qasida_number)
                probe["min_score"] = min_score
                rows = candidate_fn(**probe)
                if rows:
                    break
    search_fn = db.hybrid_search if effective_match_mode == "hybrid" else db.search
    search_args = dict(
        query=query,
        queries=raw_queries,
        operator=operator,
        search_mode=resolved_search_mode,
        ranking=ranking,
        book_ids=book_ids,
        source_code=source_code,
        page_from=page_from,
        page_to=page_to,
        limit=limit + 1,
        offset=offset,
        context_chars=context_chars,
        diversify_books=diversify_books,
        max_per_book=max_per_book,
        qasida_number=qasida_number,
    )
    search_args["min_score"] = min_score
    if match_mode != "auto":
        rows = search_fn(**search_args)

    has_more = len(rows) > limit
    results = rows[:limit]
    expand_top = max(0, min(expand_top, len(results)))
    expand_chars = max(200, min(expand_chars, 2000))
    for row in results[:expand_top]:
        row["expanded_passage"] = db.get_passage_by_match_id(
            row["match_id"], expand_chars
        )

    if mode in ("compact", "ultra_compact"):
        payload = compact_search_response(
            results,
            limit=limit,
            offset=offset,
            has_more=has_more,
            total_hits=total_hits,
            stats=stats,
            ultra=(mode == "ultra_compact"),
        )
        if include_counts and total_hits == 0 and len(raw_queries) == 1:
            suggestions = db.suggest_spelling(raw_queries[0])
            if suggestions:
                payload["suggestions"] = suggestions
        return payload

    primary_hits = sum(
        1 for result in results
        if result["source_code"] == "primary"
    )

    response = {
        "query": query,
        "queries": raw_queries,
        "operator": operator,
        "match_mode": match_mode,
        "ranking": ranking,
        "book_ids": book_ids,
        "source_code": source_code,
        "returned_count": len(results),
        "offset": offset,
        "next_offset": offset + limit if has_more else None,
        "primary_hits": primary_hits,
        "secondary_hits": len(results) - primary_hits,
        "provenance": _GRADE_REMINDER,
        "results": results,
    }
    if include_counts:
        response["total_hits"] = total_hits
        response["total_hits_unit"] = "matching_pages"
        response["total_occurrences"] = stats["matching_occurrences"]
        response["per_query"] = stats["per_query"]
    return response


app = mcp.streamable_http_app()
