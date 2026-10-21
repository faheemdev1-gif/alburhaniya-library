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
        canonical=compact_search_response(rows,limit=limit,offset=offset,has_more=has_more,
                                           total_hits=total_hits,stats=stats,ultra=False)
        aliases={value:key for key,value in BASE_FIELDS.items()}
        canonical['results']=[{aliases.get(k,k):v for k,v in hit.items()} for hit in canonical['results']]
        canonical['n']=canonical.pop('returned_count')
        if 'next_offset' in canonical:canonical['next']=canonical.pop('next_offset')
        return canonical

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
                      "intent_method", "answer_verified", "intent_evidence", "lexical_score", "also_in", "comparison_side", "synonym_variant", "reported_view", "attribution_warning", "source_role", "attribution_basis", "attribution_marker_span", "attribution_review_status", "text_errata", "subject_phrase_match", "dialogue_role", "speaker", "speaker_segments", "speaker_basis", "citation_basis", "matched_source_question", "corrects_premise", "support", "speaker_evidence", "text_version", "evidence_unit_id", "candidate_routes", "concept_coverage", "subject_match"):
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
                    **({"source_quote":row["evidence_span"]["source_quote"]} if "source_quote" in row["evidence_span"] else {}),
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
    shared=('reformulation_warning','original_queries','reformulation_method','intent_method','answer_verified','evidence_type_method','evidence_type_confidence','evidence_type_scope','match_attribution_scope','normalization_level','pagination_status','pagination_warning','reformulation_status','fewer_than_limit_reason','block_type','blk','score_kind','sk','whole_word','footnotes_excluded','selected_queries')
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
            if r.get('evidence_span'):r['evidence_span'].pop('source_quote',None)
            for key in ('intent_evidence','lexical_score','reformulated_query','page_id','intent_term_coverage','matched_source_question'):r.pop(key,None)
    if detail!='full' and not ultra:
        for meta in payload.get('books',{}).values():
            for key in ('source_author','compiler','authorship_mode'):meta.pop(key,None)
        payload['book_metadata_tool']='get_book'
    if detail!='full':
        for key in ('path','phrase_search_counts','dropped_function_words','candidate_counts','route_funnels','rejections','funnel','candidate_manifest','page_funnel'):
            payload.pop(key,None)
        if payload.get('retrieval_completeness',{}).get('status')=='not_checked':
            payload.pop('retrieval_completeness',None)
    if ultra:
        # Same provenance floor as compact. An ultra response must not require
        # get_book to discover uncertainty or whether a work is primary.
        for meta in payload.get('books',{}).values():
            if 'am' in meta:meta['authorship_mode']=meta.pop('am')
            if 'ac' in meta:meta['attribution_confidence']=meta.pop('ac')
            if detail!='full':
                for key in ('source_author','compiler','authorship_mode'):meta.pop(key,None)
        payload['results']=[{ULTRA_FIELDS.get(k,k):v for k,v in row.items()} for row in rows]
        if payload.get('result_defaults'):
            payload['result_defaults']={ULTRA_FIELDS.get(k,k):v for k,v in payload['result_defaults'].items()}
    return payload

# Published in contract v14. Every alias is reversible; unknown values, warnings
# and verification state survive projection. Compact is the canonical view.
ULTRA_FIELDS={
 'question_relevance':'qr','answer_verified':'av','support':'sup',
 'speaker_evidence':'sp','speaker_segments':'ss','speaker_basis':'sb',
 'dialogue_role':'dr','source_role':'sr','attribution_review_status':'ar',
 'evidence_span':'es','text_version':'tv','evidence_unit_id':'uid',
 'corrects_premise':'cp','concept_coverage':'cc','subject_match':'sm',
 'candidate_routes':'routes','pagination_status':'ps','pagination_warning':'pw',
 'evidence_type_method':'em','evidence_type_confidence':'ec','evidence_type_scope':'esc',
 'reformulation_warning':'rw','original_queries':'oq','reformulation_method':'rm',
 'subject_phrase_match':'pm','matched_source_question':'mq',
 'reformulation_status':'rst','intent_term_coverage':'cov',
 'match_attribution_scope':'mas','synonym_variant':'sv','reported_view':'rv',
 'attribution_warning':'aw','attribution_basis':'ab','attribution_marker_span':'ams',
 'citation_basis':'cb','text_errata':'errata',
}
BASE_FIELDS={'b':'book_id','s':'seq','m':'match_id','x':'excerpt','p':'printed_page',
 'c':'citation_label','sk':'score_kind','r':'rank','rs':'rank_score','type':'match_type',
 'blk':'block_type','et':'evidence_type','canon':'canonical_book_id','er':'edition_relation',
 'q':'qasida_number','qt':'qasida_title','bf':'bayt_from','bt':'bayt_to','qbc':'qasida_bayt_count',
 'brs':'bayt_range_scope','bn':'bayt_number','id':'stable_id','id_kind':'stable_id_kind',
 'hid':'heading_id','ids':'stable_ids','cid':'container_id','ep':'expanded_passage'}

def decode_search_response(payload):
    from copy import deepcopy
    p=deepcopy(payload);reverse={v:k for k,v in ULTRA_FIELDS.items()};reverse.update(BASE_FIELDS)
    ultra='n' in p
    defaults=p.get('result_defaults',{})
    results=[]
    for row in p.get('results',[]):
        values={**defaults,**row}
        results.append({reverse.get(k,k) if ultra else k:v for k,v in values.items()})
    return {'results':results,'books':p.get('books',{}),
            'completion':p.get('completion'),'status':p.get('status'),
            'evidence_strength':p.get('evidence_strength'),'answer_verified':p.get('answer_verified')}
