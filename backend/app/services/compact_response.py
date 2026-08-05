"""Small, model-friendly MCP response builders."""
from __future__ import annotations


def compact_search_response(
    rows: list[dict], *, limit: int, offset: int, has_more: bool,
    total_hits: int | None = None, ultra: bool = False,
) -> dict:
    """Deduplicate book metadata and retain only citation/search fields."""
    if ultra:
        books: dict[str, str] = {}
        hits = []
        for row in rows:
            books.setdefault(row["book_id"], row["book_title"])
            hit = {
                "b": row["book_id"], "s": row["seq"],
                "o": row["occurrences"], "x": row["snippet"],
            }
            if row["printed_page"] is not None:
                hit["p"] = row["printed_page"]
            hits.append(hit)
        response = {"n": len(hits), "books": books, "results": hits}
        if total_hits is not None:
            response["total"] = total_hits
        if has_more:
            response["next"] = offset + limit
        return response

    books: dict[str, dict] = {}
    hits = []
    for row in rows:
        books.setdefault(
            row["book_id"],
            {"title": row["book_title"], "source": row["source_code"]},
        )
        hit = {
            "book_id": row["book_id"], "seq": row["seq"],
            "occurrences": row["occurrences"], "excerpt": row["snippet"],
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
