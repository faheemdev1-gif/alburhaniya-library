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
 'normalization_level':'nl','footnotes_excluded':'fe','whole_word':'ww',
 'selected_queries':'sq','speaker':'sn',
}
BASE_FIELDS={'b':'book_id','s':'seq','m':'match_id','x':'excerpt','p':'printed_page',
 'c':'citation_label','sk':'score_kind','r':'rank','rs':'rank_score','type':'match_type',
 'blk':'block_type','et':'evidence_type','canon':'canonical_book_id','er':'edition_relation',
 'q':'qasida_number','qt':'qasida_title','bf':'bayt_from','bt':'bayt_to','qbc':'qasida_bayt_count',
 'brs':'bayt_range_scope','bn':'bayt_number','id':'stable_id','id_kind':'stable_id_kind',
 'hid':'heading_id','ids':'stable_ids','cid':'container_id','ep':'expanded_passage'}

def decode_search_response(payload):
    from copy import deepcopy
    p=deepcopy(payload)
    if p.get('encoding') == 'lossless-15':
        p = decode_minimal(p)
    reverse={v:k for k,v in ULTRA_FIELDS.items()};reverse.update(BASE_FIELDS)
    ultra='n' in p
    defaults=p.get('result_defaults',{})
    results=[]
    for row in p.get('results',[]):
        values={**defaults,**row}
        results.append({reverse.get(k,k) if ultra else k:v for k,v in values.items()})
    return {'results':results,'books':p.get('books',{}),
            'completion':p.get('completion'),'status':p.get('status'),
            'evidence_strength':p.get('evidence_strength'),'answer_verified':p.get('answer_verified')}


def project_search_response(canonical, *, mode, detail, expand_top, expand_chars):
    """Render one cached canonical evidence set without another retrieval call."""
    from copy import deepcopy
    from app.services import library_db as db
    payload = deepcopy(canonical)
    rows = payload['results']
    defaults = payload.pop('result_defaults', {})
    payload['results'] = rows = [{**defaults, **r} for r in rows]
    attach_expanded_passages(rows, expand_top=0 if payload.get('completion')=='partial' else expand_top, expand_chars=expand_chars,
                             passage_loader=db.get_passage_by_match_id)
    slim_response(payload, detail=detail, ultra=False)
    if mode == 'ultra_compact':
        aliases = {value:key for key,value in BASE_FIELDS.items()}
        aliases.update(ULTRA_FIELDS)
        payload['results'] = [{aliases.get(k,k):v for k,v in r.items()} for r in payload['results']]
        if payload.get('result_defaults'):
            payload['result_defaults'] = {aliases.get(k,k):v for k,v in payload['result_defaults'].items()}
        payload['n'] = payload.pop('returned_count')
        if 'next_offset' in payload:payload['next'] = payload.pop('next_offset')
        if detail != 'full':payload = encode_minimal(payload)
    return payload


# Contract 15's lossless minimal representation. Codes replace only fixed
# vocabulary, never remove uncertainty. Full detail retains ordinary objects.
VALUE_CODES = (
    'unreviewed','unknown','structural','explicit_marker','none','answer','question','mixed',
    'source_local_rules_v1','candidate','topical','relation_candidate','topic_only',
    'phrase_candidate','start_anchor','structural_heuristic','unverified',
    'Candidate discovery only; inspect the Arabic passage before using it as an answer.',
    'phrase_and_passage_union_v1','local_span_discovery','reformulated','safe','broad_discovery',
    'body_only','only_n_passages_met_threshold','repeated_printed_label_unresolved',
    'Printed page label is repeated in the supplied source; cite sequence until reviewed.',
    'explicit_question_marker','answer_marker_author_not_inferred',
    'implicit_answer_after_question_mark','explicit_marker_author_not_inferred',
    'lexical','exact_phrase','terms','verified','primary','confirmed','pending_documentary_review',
)
NESTED_KEYS = {
    'anchor_role':'a','passage_role':'p','basis':'b','review_status':'r','name':'n','segments':'s',
    'estimate':'e','method':'m','calibrated':'c','start':'s0','end':'e0','role':'r0',
    'speaker':'sp0','marker':'mk','scope':'sc','confidence':'cf',
    'corpus_form':'f','relation':'l',
}
CODE_SYMBOLS='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
ENVELOPE_KEYS={'result_defaults':'defaults','effective_match_mode':'mm',
 'navigation_scope':'nav','reformulation_status':'rst','fewer_than_limit_reason':'why',
 'evidence_strength':'strength','answer_verified':'av','book_defaults':'bd',
 'objects':'o','qasidas':'qs'}
BOOK_KEYS={'title':'t','source':'s','tier':'i','attribution_confidence':'a','provenance_status':'p'}

def _code(value, decode=False):
    if isinstance(value, dict):return {k:_code(v,decode) for k,v in value.items()}
    if isinstance(value, list):return [_code(v,decode) for v in value]
    if not isinstance(value,str):return value
    if decode:
        if value.startswith('~'):return value[1:]
        if len(value)==1 and value in CODE_SYMBOLS[:len(VALUE_CODES)]:return VALUE_CODES[CODE_SYMBOLS.index(value)]
        return value
    if value in VALUE_CODES:return CODE_SYMBOLS[VALUE_CODES.index(value)]
    return '~'+value if value.startswith('~') or len(value)==1 and value in CODE_SYMBOLS[:len(VALUE_CODES)] else value

def _nested(value, decode=False):
    keys = {v:k for k,v in NESTED_KEYS.items()} if decode else NESTED_KEYS
    if isinstance(value,dict):return {keys.get(k,k):_nested(v,decode) for k,v in value.items()}
    if isinstance(value,list):return [_nested(v,decode) for v in value]
    return value

def encode_minimal(payload):
    """Factor repeated evidence metadata; preserve a mechanically exact inverse."""
    import re
    rows=payload['results'];defaults=payload.setdefault('result_defaults',{})
    for index,row in enumerate(rows,1):
        title=payload.get('books',{}).get(row.get('b'),{}).get('title')
        if title and row.get('p') is not None and row.get('c')==f"{title}، الصفحة {row['p']}":
            row['c']='@printed'
        m=re.fullmatch(r'(b\d+)-p(\d+)-c\d+',row.get('m',''))
        if m and row.get('b')==m[1] and row.get('s')==int(m[2]):
            row.pop('b');row.pop('s')
        if row.get('r')==index:row.pop('r')
        if row.get('ss') is not None and row.get('sp',{}).get('segments')==row['ss']:
            row['ss']='@sp'
    # Several page hits can belong to one qasida. Keep its identity/length once
    # while each page retains its own printed label, bayt range and source span.
    qasidas={}
    for row in rows:
        if 'q' not in row:continue
        fields={k:row[k] for k in ('q','qt','qbc','cid') if k in row}
        key=str(row['q'])
        if key in qasidas and qasidas[key]!=fields:continue
        qasidas[key]=fields;row['qref']=key
        for k in fields:row.pop(k)
    if qasidas:payload['qasidas']=qasidas
    # Expanded passages can inherit only identical values from their own hit;
    # source text and context boundaries remain in the expansion itself.
    for row in rows:
        expansion=row.get('ep')
        if not isinstance(expansion,dict):continue
        inherited=[]
        for alias,field in BASE_FIELDS.items():
            if field in expansion and alias in row and expansion[field]==row[alias]:
                inherited.append(field);expansion.pop(field)
        if inherited:expansion['from_hit']=inherited
    # Shared unknown/false/review values stay explicit through inheritance.
    excluded={'m','x','s','b','r','es','tv','uid','p','c','id','ep','qref','ss'}
    for key in set.intersection(*(set(r) for r in rows)) if rows else ():
        if key not in excluded and all(r[key]==rows[0][key] for r in rows):
            defaults[key]=rows[0][key]
            for row in rows:row.pop(key)
    for row in [defaults,*rows]:
        for key in ('sup','sp','ss','cb','ams','sv','matched_terms'):
            if key in row:row[key]=_nested(row[key])
        if isinstance(row.get('es'),dict):
            span=row['es'];row['es']=[span['start'],span['end']]+([span['source_quote']] if 'source_quote' in span else [])
    payload['encoding']='lossless-15'
    books=list(payload.get('books',{}).values())
    common={k:books[0][k] for k in set.intersection(*(set(b) for b in books))
            if all(b[k]==books[0][k] for b in books)} if books else {}
    if common:
        payload['book_defaults']=common
        for book in books:
            for key in common:book.pop(key)
    # Exact object interning removes repeated speaker and morphology records.
    # Integers in these object-valued fields are references into this response.
    import json
    pool=[];targets=('sp','matched_terms','sup')
    for key in targets:
        occurrences={}
        for row in rows:
            if isinstance(row.get(key),dict):
                serial=json.dumps(row[key],ensure_ascii=False,sort_keys=True,separators=(',',':'))
                occurrences.setdefault(serial,[]).append(row)
        for serial,group in occurrences.items():
            if len(group)>1 and len(serial)>35:
                ref=len(pool);pool.append(group[0][key])
                for row in group:row[key]=ref
    if pool:payload['objects']=pool
    payload['books']={k:{BOOK_KEYS.get(f,f):v for f,v in b.items()} for k,b in payload.get('books',{}).items()}
    if 'book_defaults' in payload:payload['book_defaults']={BOOK_KEYS.get(f,f):v for f,v in payload['book_defaults'].items()}
    payload={ENVELOPE_KEYS.get(k,k):v for k,v in payload.items()}
    return _code(payload)

def decode_minimal(payload):
    import re
    payload=_code(payload,True)
    if 'versions' in payload:
        names={'i':'index','l':'lexicon','c':'cues','r':'ranker'}
        payload['versions']={names.get(k,k):v for k,v in payload['versions'].items()}
    reverse={v:k for k,v in ENVELOPE_KEYS.items()}
    payload={reverse.get(k,k):v for k,v in payload.items()}
    reverse_books={v:k for k,v in BOOK_KEYS.items()}
    payload['books']={k:{reverse_books.get(f,f):v for f,v in b.items()} for k,b in payload.get('books',{}).items()}
    if 'book_defaults' in payload:payload['book_defaults']={reverse_books.get(f,f):v for f,v in payload['book_defaults'].items()}
    pool=payload.pop('objects',[])
    from copy import deepcopy
    for row in payload.get('results',[]):
        for key in ('sp','matched_terms','sup'):
            if isinstance(row.get(key),int):row[key]=deepcopy(pool[row[key]])
    for row in [payload.get('result_defaults',{}),*payload.get('results',[])]:
        for key in ('sup','sp','ss','cb','ams','sv','matched_terms'):
            if key in row:row[key]=_nested(row[key],True)
        if isinstance(row.get('es'),list):
            s=row['es'];row['es']={'start':s[0],'end':s[1],**({'source_quote':s[2]} if len(s)>2 else {})}
    defaults=payload.pop('result_defaults',{})
    payload['results']=[{**deepcopy(defaults),**row} for row in payload.get('results',[])]
    for index,row in enumerate(payload.get('results',[]),1):
        m=re.fullmatch(r'(b\d+)-p(\d+)-c\d+',row.get('m',''))
        if m:row.setdefault('b',m[1]);row.setdefault('s',int(m[2]))
        row.setdefault('r',index)
        if row.get('ss')=='@sp':row['ss']=row.get('sp',{}).get('segments',[])
        if 'qref' in row:row.update(payload.get('qasidas',{})[row.pop('qref')])
        if isinstance(row.get('ep'),dict):
            expansion=row['ep'];aliases={v:k for k,v in BASE_FIELDS.items()}
            for field in expansion.pop('from_hit',[]):expansion[field]=row[aliases[field]]
    common=payload.pop('book_defaults',{})
    payload['books']={key:{**common,**value} for key,value in payload.get('books',{}).items()}
    for row in payload.get('results',[]):
        if row.get('c')=='@printed':row['c']=f"{payload['books'][row['b']]['title']}، الصفحة {row['p']}"
    return payload


def encoding_guide():
    """Complete decoder legend in tools/list; no extra metadata call needed."""
    return {'id':'lossless-15','hit_aliases':{**BASE_FIELDS,**{v:k for k,v in ULTRA_FIELDS.items()}},
      'envelope_keys':ENVELOPE_KEYS,'book_keys':BOOK_KEYS,'nested_keys':NESTED_KEYS,
      'codes':dict(zip(CODE_SYMBOLS,VALUE_CODES)),
      'rules':'Decode codes in string values only; prefix ~ escapes a literal. Expand defaults, bd book defaults, o object references (sp/matched_terms/sup), qs qasidas by qref, then aliases. es=[start,end,optional quote]. Absent b/s derive from m=bNN-pSEQ-cOFFSET; absent r is 1-based array order. c=@printed expands as book title + ، الصفحة + p. ss=@sp copies sp.segments; ep.from_hit names exactly inherited hit fields. contract v/d/t=version/capability digest/schema digest (8-char prefixes); timing.ms=total ms; versions i/l/c/r=index/lexicon/cues/ranker. Unknown and unreviewed stay explicit; never infer a verified answer.'}
