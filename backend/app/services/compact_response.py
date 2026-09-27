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
            books.setdefault(row["book_id"], {
                "title": row["book_title"], "tier": row["source_tier"],
                "am": row.get("authorship_mode"),
                "ac": row.get("attribution_confidence"),
                "source": row.get("source_code"),
                "source_author": row.get("source_author"),
                "compiler": row.get("compiler"),
                "provenance_status": row.get("provenance_status"),
            })
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
            if row.get("evidence_type"):
                hit["et"] = row["evidence_type"]
            if row.get("canonical_book_id") and row["canonical_book_id"] != row["book_id"]:
                hit["canon"] = row["canonical_book_id"]
                hit["er"] = row.get("edition_relation")
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
            if "matched_terms" in row:
                hit["matched_terms"] = {
                    query: {key: value for key, value in evidence.items()
                            if key not in {"surface_form", "normalized_form"}}
                    for query, evidence in row["matched_terms"].items()
                }
            for field in ("selected_queries", "match_attribution_scope", "evidence_type_method", "evidence_type_confidence", "original_queries",
                      "intent_term_coverage", "reformulation_warning", "question_relevance",
                      "reformulation_status", "page_id", "pagination_status", "pagination_warning", "evidence_type_scope",
                      "intent_method", "answer_verified", "intent_evidence", "lexical_score", "alternate_locations", "also_in", "reported_view", "attribution_warning", "text_errata", "subject_phrase_match", "dialogue_role", "speaker", "speaker_basis", "citation_basis", "matched_source_question"):
                if field in row:
                    hit[field] = row[field]
            if row.get("reformulated_query"):
                hit["reformulated_query"] = row["reformulated_query"]
                hit["reformulation_method"] = row.get("reformulation_method")
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
            response["census_matching_pages"] = total_hits
        if stats:
            response["census_occurrences"] = stats["matching_occurrences"]
            response["count_basis"] = stats["count_basis"]
            response["count_semantics"] = {
                "whole_word": stats["whole_word"],
                "normalization_level": stats["normalization_level"],
                "footnotes_excluded": stats["footnotes_excluded"],
            }
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
        books[row["book_id"]].update({
            "source_author": row.get("source_author"),
            "compiler": row.get("compiler"),
            "authorship_mode": row.get("authorship_mode"),
            "attribution_confidence": row.get("attribution_confidence"),
            "provenance_status": row.get("provenance_status"),
        })
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
                      "block_type", "evidence_type", "matched_terms",
                      "whole_word", "normalization_level", "footnotes_excluded",
                      "reformulated_query", "reformulation_method", "selected_queries",
                      "match_attribution_scope", "evidence_type_method", "evidence_type_confidence", "original_queries",
                      "intent_term_coverage", "reformulation_warning", "question_relevance",
                      "reformulation_status", "page_id", "pagination_status", "pagination_warning", "evidence_type_scope",
                      "intent_method", "answer_verified", "intent_evidence", "lexical_score", "alternate_locations", "also_in", "reported_view", "attribution_warning", "text_errata", "subject_phrase_match", "dialogue_role", "speaker", "speaker_basis", "citation_basis", "matched_source_question"):
            if row.get(field) is not None:
                hit[field] = row[field]
        if row.get("canonical_book_id") and row["canonical_book_id"] != row["book_id"]:
            hit["canonical_book_id"] = row["canonical_book_id"]
            hit["edition_relation"] = row.get("edition_relation")
            hit["searchable_by_default"] = bool(row.get("searchable_by_default"))
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
        response["census_matching_pages"] = total_hits
    if stats:
        response["census_occurrences"] = stats["matching_occurrences"]
        response["count_basis"] = stats["count_basis"]
        response["count_semantics"] = {
            "whole_word": stats["whole_word"],
            "normalization_level": stats["normalization_level"],
            "footnotes_excluded": stats["footnotes_excluded"],
        }
        response["per_query"] = stats["per_query"]
    if has_more:
        response["next_offset"] = offset + limit
    return response

def slim_response(payload,*,detail='summary',ultra=False):
    """Contract 11: row values inherit explicitly declared response defaults."""
    rows=payload.get('results',[])
    shared=('reformulation_warning','original_queries','reformulation_method','intent_method','answer_verified','evidence_type_method','evidence_type_confidence','evidence_type_scope','match_attribution_scope','normalization_level','pagination_status','pagination_warning','reformulation_status','block_type','blk','score_kind','sk','whole_word','footnotes_excluded','selected_queries')
    defaults={}
    for key in shared:
        if rows and all(key in r and r[key]==rows[0].get(key) for r in rows):
            defaults[key]=rows[0][key]
            for r in rows:r.pop(key)
    if defaults:payload['result_defaults']=defaults
    if detail!='full':
        payload.pop('query_plan',None)
        for r in rows:
            for evidence in r.get('matched_terms',{}).values():
                for key in ('surface_form','normalized_form','safe_normalized_form','query_normalized'):evidence.pop(key,None)
            for key in ('intent_evidence','lexical_score','reformulated_query','page_id','intent_term_coverage','matched_source_question'):r.pop(key,None)
    if detail!='full' and not ultra:
        for meta in payload.get('books',{}).values():
            for key in ('source_author','compiler','authorship_mode'):meta.pop(key,None)
        payload['book_metadata_tool']='get_book'
    if ultra:
        payload['books']={bid:{'tier':meta['tier']} for bid,meta in payload.get('books',{}).items()};payload['book_metadata_tool']='get_book'
    return payload
