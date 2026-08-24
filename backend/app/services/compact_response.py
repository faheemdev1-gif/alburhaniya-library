"""Small, model-friendly MCP response builders."""
from __future__ import annotations

from collections.abc import Callable


def attach_expanded_passages(
    rows: list[dict], *, expand_top: int, expand_chars: int,
    passage_loader: Callable[[str, int], dict | None],
) -> int:
    """Attach exactly the requested number of valid focused passages.

    Invalid/unknown match ids are made explicit instead of silently reducing
    the number of expansions, which previously made ``expand_top`` difficult
    for clients to reason about.
    """
    requested = max(0, min(int(expand_top), len(rows)))
    bounded_chars = max(200, min(int(expand_chars), 2000))
    for row in rows[:requested]:
        match_id = row.get("match_id")
        passage = passage_loader(match_id, bounded_chars) if match_id else None
        row["expanded_passage"] = passage or {
            "error": f"invalid or unknown match_id '{match_id}'"
        }
    return requested


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
                "type": row["match_type"], "sk": row.get("score_kind"),
                "r": row.get("rank"),
            }
            if row.get("rank_score") is not None:
                hit["rs"] = row["rank_score"]
            if row["printed_page"] is not None:
                hit["p"] = row["printed_page"]
            if row.get("citation_label"):
                hit["c"] = row["citation_label"]
            # ``bt`` is already the public abbreviation for ``bayt_to``.
            # Keep structural classification unambiguous under ``blk``.
            if row.get("block_type"):
                hit["blk"] = row["block_type"]
            if row.get("qasida_number") is not None:
                hit["q"] = row["qasida_number"]
            if row.get("qasida_title"):
                hit["qt"] = row["qasida_title"]
            if row.get("bayt_from") is not None:
                hit["bf"] = row["bayt_from"]
            if row.get("bayt_to") is not None:
                hit["bt"] = row["bayt_to"]
            if row.get("qasida_bayt_count") is not None:
                hit["qbc"] = row["qasida_bayt_count"]
            if row.get("bayt_range_scope"):
                hit["brs"] = row["bayt_range_scope"]
            if row.get("bayt_number") is not None:
                hit["bn"] = row["bayt_number"]
            if row.get("stable_id"):
                hit["id"] = row["stable_id"]
            if row.get("stable_id_kind"):
                hit["id_kind"] = row["stable_id_kind"]
            if row.get("heading_id"):
                hit["hid"] = row["heading_id"]
            if row.get("stable_ids"):
                hit["ids"] = row["stable_ids"]
            if row.get("container_id"):
                hit["cid"] = row["container_id"]
            if row.get("semantic_score") is not None:
                hit["semantic_score"] = row["semantic_score"]
                hit["citation_verified"] = bool(row.get("citation_verified"))
                hit["verification_required"] = bool(row.get("verification_required"))
            if row.get("matched_terms"):
                hit["matched_terms"] = row["matched_terms"]
            if row.get("evidence_span"):
                hit["evidence_span"] = {
                    "start": row["evidence_span"]["start"],
                    "end": row["evidence_span"]["end"],
                }
            # Preserve an explicitly requested expansion in every supported
            # mode. ``ep`` keeps the ultra-compact envelope concise.
            if row.get("expanded_passage"):
                hit["ep"] = row["expanded_passage"]
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
            "score_kind": row.get("score_kind"), "rank": row.get("rank"),
            "match_type": row["match_type"],
        }
        if row.get("rank_score") is not None:
            hit["rank_score"] = row["rank_score"]
        if row["printed_page"] is not None:
            hit["printed_page"] = row["printed_page"]
        if row.get("citation_label"):
            hit["citation_label"] = row["citation_label"]
        for field in ("qasida_number", "qasida_title", "qasida_bayt_count",
                      "bayt_from", "bayt_to", "page_bayt_from", "page_bayt_to",
                      "bayt_range_scope", "bayt_number", "stable_id",
                      "stable_id_kind", "heading_id", "stable_ids", "container_id",
                      "block_type", "matched_terms"):
            if row.get(field) is not None:
                hit[field] = row[field]
        if row.get("evidence_span"):
            hit["evidence_span"] = {
                "start": row["evidence_span"]["start"],
                "end": row["evidence_span"]["end"],
            }
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
