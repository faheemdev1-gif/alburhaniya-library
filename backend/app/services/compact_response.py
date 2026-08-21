"""Small, model-friendly MCP response builders."""
from __future__ import annotations


def compact_search_response(
    rows: list[dict], *, limit: int, offset: int, has_more: bool,
    total_hits: int | None = None, stats: dict | None = None, ultra: bool = False,
) -> dict:
    """Deduplicate book metadata and retain only citation/search fields."""
    if ultra:
        books: dict[str, str] = {}
        hits = []
        for row in rows:
            books.setdefault(row["book_id"], {"title": row["book_title"], "tier": row["source_tier"]})
            hit = {
                "b": row["book_id"], "s": row["seq"],
                "m": row["match_id"], "x": row["snippet"], "score": row["score"],
                "type": row["match_type"],
            }
            if row["printed_page"] is not None:
                hit["p"] = row["printed_page"]
            elif row.get("citation_label"):
                hit["c"] = row["citation_label"]
            if row.get("qasida_number") is not None:
                hit["q"] = row["qasida_number"]
            if row.get("qasida_title"):
                hit["qt"] = row["qasida_title"]
            if row.get("bayt_from") is not None:
                hit["bf"] = row["bayt_from"]
            if row.get("bayt_to") is not None:
                hit["bt"] = row["bayt_to"]
            if row.get("bayt_number") is not None:
                hit["bn"] = row["bayt_number"]
            if row.get("stable_id"):
                hit["id"] = row["stable_id"]
            if row.get("semantic_score") is not None:
                hit["semantic_score"] = row["semantic_score"]
                hit["citation_verified"] = bool(row.get("citation_verified"))
                hit["verification_required"] = bool(row.get("verification_required"))
            if row.get("matched_terms"):
                hit["matched_terms"] = row["matched_terms"]
            if row.get("evidence_span"):
                hit["evidence_span"] = row["evidence_span"]
            hits.append(hit)
        response = {"n": len(hits), "books": books, "results": hits}
        if total_hits is not None:
            response["total"] = total_hits
            response["total_unit"] = "matching_pages"
        if stats:
            response["occurrences"] = stats["matching_occurrences"]
            response["per_query"] = stats["per_query"]
        if has_more:
            response["next"] = offset + limit
        return response

    books: dict[str, dict] = {}
    hits = []
    for row in rows:
        books.setdefault(
            row["book_id"],
            {"title": row["book_title"], "source": row["source_code"], "tier": row["source_tier"]},
        )
        hit = {
            "book_id": row["book_id"], "seq": row["seq"],
            "match_id": row["match_id"], "excerpt": row["snippet"], "score": row["score"],
            "match_type": row["match_type"],
        }
        if row["printed_page"] is not None:
            hit["printed_page"] = row["printed_page"]
        elif row.get("citation_label"):
            hit["citation_label"] = row["citation_label"]
        for field in ("qasida_number", "qasida_title", "bayt_from", "bayt_to",
                      "bayt_number", "stable_id", "block_type", "matched_terms",
                      "evidence_span"):
            if row.get(field) is not None:
                hit[field] = row[field]
        if row.get("semantic_score") is not None:
            hit["semantic_score"] = row["semantic_score"]
            hit["citation_verified"] = bool(row.get("citation_verified"))
            hit["verification_required"] = bool(row.get("verification_required"))
        hits.append(hit)
        if row.get("expanded_passage"):
            hit["expanded_passage"] = row["expanded_passage"]

    response = {"returned_count": len(hits), "books": books, "results": hits}
    if total_hits is not None:
        response["total_hits"] = total_hits
        response["total_hits_unit"] = "matching_pages"
    if stats:
        response["total_occurrences"] = stats["matching_occurrences"]
        response["per_query"] = stats["per_query"]
    if has_more:
        response["next_offset"] = offset + limit
    return response
