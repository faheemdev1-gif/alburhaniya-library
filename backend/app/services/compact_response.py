"""Small, model-friendly MCP response builders.

Kept independent of the MCP runtime so the token contract can be tested
without starting a web server.
"""
from __future__ import annotations


def compact_search_response(
    rows: list[dict], *, limit: int, offset: int, has_more: bool,
    total_hits: int | None = None,
) -> dict:
    """Deduplicate book metadata and retain only citation/search fields."""
    books: dict[str, dict] = {}
    hits = []
    for row in rows:
        books.setdefault(
            row["book_id"],
            {"title": row["book_title"], "source": row["source_code"]},
        )
        hit = {
            "book_id": row["book_id"],
            "seq": row["seq"],
            "occurrences": row["occurrences"],
            "excerpt": row["snippet"],
        }
        if row["printed_page"] is not None:
            hit["printed_page"] = row["printed_page"]
        hits.append(hit)

    response = {"returned_count": len(hits), "books": books, "results": hits}
    if total_hits is not None:
        response["total_hits"] = total_hits
    if has_more:
        response["next_offset"] = offset + limit
    return response
