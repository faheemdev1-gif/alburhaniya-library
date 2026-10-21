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

from app.core.text_format import format_page, repair_quran_display_brackets
from app.core.resilience import safe_tool_call
from app.core.observability import candidate_snapshot, query_candidate_snapshot
from app.mcp_contract import (
    REQUIRED_TOOLS,
    SERVER_VERSION,
    TOOL_CONTRACT_ID,
    TOOL_CONTRACT_VERSION,
    TOOL_META,
    contract_metadata,
    validate_registered_tools,
    bind_callable_schema,
)
from app.services import library_db as db
from app.services.compact_response import attach_expanded_passages, compact_search_response
from app.services.corpus_contract import corpus_contract_snapshot


_RENDER_HOST = "burhaniya-library-backend.onrender.com"

ResponseMode = Literal["compact", "ultra_compact"]
CountBasis = Literal["phrase", "term_bag"]

_GRADE_REMINDER = "primary=authoritative; secondary=supporting only"
mcp = FastMCP(
    "burhaniya-library",
    instructions=(
        "Al Burhania exposes exactly five research tools: search_library, "
        "get_passage, get_page, get_book, and list_books. If fewer than these "
        "five tools are available, connector discovery is incomplete: report "
        "the missing tool instead of redefining Al Burhania as having fewer "
        "tools. Always use search_library first, then call get_passage with a "
        "returned match_id. Use get_page only when the whole "
        "page is genuinely needed. Do not retrieve pages "
        "sequentially unless the question requires adjacent context. Prefer "
        "primary sources; secondary sources are supporting commentary. Never "
        "attribute secondary interpretation directly to a shaykh. Cite the "
        "book and printed page, or seq when no printed page exists. Exact and "
        "explicitly audited lexeme results are citation-capable. Auto results "
        "are citation-capable only when match_type and matched_terms establish "
        "the evidence relation. Surface text is authoritative for quotation; "
        "normalization can collapse distinct ى/ي forms. "
        "Literal exact/terms/count operations default to whole-word matching "
        "and safe normalization: hamza, ى/ي, and ة/ه remain distinct. Broad "
        "normalization is discovery-only and its evidence relation must be "
        "inspected. Counts declare count_basis and never inherit their meaning "
        "silently from retrieval mode. retrieval_hit_count, "
        "literal_matching_pages, and literal_occurrences are distinct; a zero "
        "literal phrase count can coexist with broader retrieval results. Long "
        "questions may expose a deterministic reformulated_query. A zero result is not proof of absence; "
        "inspect diagnostics. "
        "For Dīwān results, bayt_from and bayt_to are page-scoped; use "
        "qasida_bayt_count for the complete qaṣīda length. TOC/fihris hits "
        "are explicitly typed and downranked. "
        "Verify the identified speaker and compiler before attribution. "
        f"Tool contract: {TOOL_CONTRACT_ID}; contract version: "
        f"{TOOL_CONTRACT_VERSION}; required tool count: {len(REQUIRED_TOOLS)}."
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

# FastMCP 1.x otherwise reports the SDK package version during initialize,
# which makes connector-cache diagnostics misleading.  The low-level server
# owns the protocol serverInfo object, so set the application release there.
mcp._mcp_server.version = SERVER_VERSION
if mcp._mcp_server.version != SERVER_VERSION:  # pragma: no cover - fail loud
    raise RuntimeError("MCP application version was not applied to serverInfo")


from app.core.evidence_blocks import navigation_scope

@mcp.tool(structured_output=True, meta=TOOL_META)
@safe_tool_call
def list_books(include_legend: bool = False, projection: Literal["compact", "ids", "full"] = "compact",
               book_ids: Optional[list[str]] = None) -> dict[str, Any]:
    """List books in a compact catalogue, ordered by source authority.

    This is one of the five required Al Burhania research tools. The response
    also reports the live connector and corpus contracts so an MCP-only client
    can verify the release, five-tool manifest, corpus totals, Dīwān sweep,
    and stable-ID integrity without access to the HTTP health endpoint.
    Non-canonical editions remain listed with canonical_book_id and
    searchable_by_default metadata.

    Args:
        include_legend: Include full source-grade definitions. Leave false
            unless the detailed definitions are specifically required.
        projection: compact catalogue, ids only, or full provenance metadata.
        book_ids: Optional IDs to filter or batch-load full metadata (maximum 43).
    """
    catalogue = db.list_books()
    if book_ids is not None:
        unknown = set(book_ids) - {b["book_id"] for b in catalogue}
        if unknown or len(book_ids) > 43:
            raise ValueError("Unknown book_ids or more than 43 IDs requested")
        catalogue = [b for b in catalogue if b["book_id"] in book_ids]
    books = [
        ({
            "id": book["book_id"],
            "title": book["title"],
            "pages": book["page_count"],
            "source": book["source_code"],
            "tier": book["source_tier"],
            "authorship_mode": book["authorship_mode"],
            "attribution_confidence": book["attribution_confidence"],
        } | ({
            "canonical_book_id": book["canonical_book_id"],
            "edition_relation": book["edition_relation"],
            "searchable_by_default": bool(book["searchable_by_default"]),
        } if book["canonical_book_id"] != book["book_id"] else {}))
        for book in catalogue
    ]
    if projection == "ids":
        return {"books":[b["book_id"] for b in catalogue],"contract_digest":TOOL_META.get("tool_schema_digest",TOOL_META["schema_digest"])}
    elif projection == "full":
        books = [db.get_book(b["book_id"]) for b in catalogue]
    elif projection != "compact":
        raise ValueError("projection must be compact, ids, or full")

    result = {
        "total": len(books),
        "books": books,
        # MCP-only clients cannot call the HTTP /health route. Publish the
        # same live-computed evidence here without adding a sixth tool.
        "connector_contract": contract_metadata(REQUIRED_TOOLS),
        "corpus_contract": corpus_contract_snapshot(),
    }

    if projection!="full":result["corpus_contract"].pop("repeated_printed_labels",None)
    from app.services import semantic_search as semantic
    result["active_indexes"] = {
        "lexical": "sqlite_fts5_safe",
        "lexeme_policy": db.LEXEME_POLICY_VERSION,
        "semantic_active": semantic.semantic_available(),
        "semantic_policy": "Disabled by default; enable only with rebuilt chunks, matching corpus hash/vector dimensions and the query model installed.",
        "root_coverage_meaning": "Tokens with a curated root annotation, not a retrieval recall percentage. Lexeme retrieval does not require root annotations.",
    }
    if include_legend:
        result["grades"] = db.get_grades()
        result["tiers"] = db.get_tiers()

    return result


@mcp.tool(structured_output=True, meta=TOOL_META)
@safe_tool_call
def get_book(book_id: str) -> dict[str, Any]:
    """Get the metadata and provenance of one book.

    This is one of the five required Al Burhania research tools. The response
    includes the live connector contract for MCP-only version verification.

    Args:
        book_id: Book ID returned by list_books, such as "b33".
    """
    book = db.get_book(book_id)

    if book is None:
        return {
            "error": f"no book with id '{book_id}'",
        }

    book["searchable_by_default"] = bool(book["searchable_by_default"])
    book["review_basis"] = {"status":"documentary_review_pending","basis":book.get("provenance_status"),"reviewer":None,"review_date":None}
    book["connector_contract"] = contract_metadata(REQUIRED_TOOLS)
    return book


@mcp.tool(structured_output=True, meta=TOOL_META)
@safe_tool_call
def get_page(
    book_id: str,
    seq: int,
    mode: ResponseMode = "compact",
    max_chars: int = 20000,
) -> dict[str, Any]:
    """Read one specific full page.

    Use this only after search_library identifies a relevant result. Use
    get_passage instead when a precise structural passage is sufficient.

    Args:
        book_id: Book ID returned by search_library or list_books.
        seq: Page sequence number, starting at 1.
        mode: Response shape. Supported values are "compact" and
            "ultra_compact" only.
        max_chars: Explicit safety cap. Defaults to 20,000, which currently
            returns every indexed page in full. Any truncation is declared.
    """
    page = db.get_page(book_id, seq)

    if page is None:
        return {
            "error": f"no page {seq} in book '{book_id}'",
        }

    if page.get('pagination_status')=='repeated_printed_label_unresolved':page['printed_page']=None
    from app.core.attribution import REPORTED, attribution_at
    # A page can contain opposing speakers. Preserve the original offsets so
    # the reader can locate guarded statements in the unformatted source.
    page["attribution_guards"] = [
        {"anchor": m.start(), **guard}
        for m in REPORTED.finditer(page["text"])
        if (guard := attribution_at(page["text"], m.end())).get("reported_view")
    ]

    # Canonical page text is the coordinate authority. Display transforms belong
    # in HTML views; they must never invalidate search/attribution offsets.
    repaired_brackets = False
    requested_max_chars = max_chars
    max_chars = max(1, min(max_chars, 20000))
    full_chars = len(page["text"])
    oversized = full_chars > max_chars
    if oversized:
        page["text"] = page["text"][:max_chars-1] + "…"

    if mode in ("compact", "ultra_compact"):
        result = {
            "book_id": page["book_id"],
            "book_title": page["book_title"],
            "source": page["source_code"],
            "tier": page["source_tier"],
            "seq": page["seq"],
            "text": page["text"],
            "coordinate_contract": page["coordinate_contract"],
            "full_chars": full_chars,
            "requested_max_chars": requested_max_chars,
            "effective_max_chars": max_chars,
            "truncated": bool(oversized),
            "source_author": page.get("source_author"),
            "compiler": page.get("compiler"),
            "authorship_mode": page.get("authorship_mode"),
            "attribution_confidence": page.get("attribution_confidence"),
            "provenance_status": page.get("provenance_status"),
            "content_types": page.get("content_types", ["body"]),
            "attribution_guards": page["attribution_guards"],
        }

        if page["printed_page"] is not None:
            result["printed_page"] = page["printed_page"]
        if page.get("citation_label"):
            result["citation_label"] = page["citation_label"]

        for field in (
            "qasida_number", "qasida_title", "qasida_bayt_count",
            "bayt_from", "bayt_to", "block_type", "canonical_book_id",
            "edition_relation", "searchable_by_default", "page_id",
            "pagination_status", "pagination_warning", "evidence_blocks",
        ):
            if page.get(field) is not None:
                result[field] = page[field]
        if page.get("bayt_from") is not None:
            result["page_bayt_from"] = page["bayt_from"]
            result["page_bayt_to"] = page["bayt_to"]
            result["bayt_range_scope"] = "page"

        if page["has_next"]:
            result["next_seq"] = page["seq"] + 1
        if oversized:
            result["hint"] = "Use get_passage for focused context or raise max_chars deliberately."
        if repaired_brackets:
            result["display_repairs"] = ["quran_bracket_direction"]

        if mode == "ultra_compact":
            # Keep canonical locators and full text; omit book-level repetition.
            for key in ("book_title","source_author","compiler","canonical_book_id",
                        "edition_relation","content_types","evidence_blocks","hint"):
                result.pop(key,None)
            result["metadata_tool"] = "get_book"
        return result

    return page


@mcp.tool(structured_output=True, meta=TOOL_META)
@safe_tool_call
def get_passage(
    match_id: Optional[str] = None,
    match_ids: Optional[list[str]] = None,
    context_chars: int = 600,
    query: Optional[str] = None,
    stable_id: Optional[str] = None,
    qasida_number: Optional[int] = None,
    include_parallels: bool = False,
    parallel_limit: int = 5,
    context_mode: Literal["bounded", "paragraph"] = "bounded",
    max_chars: int = 12000,
) -> dict[str, Any]:
    """Read one or several bounded passages returned by search_library.

    This is the preferred second step after search_library when a result
    identifies a precise passage and a full page is unnecessary. It also
    provides full qaṣīda context without adding a sixth tool: pass
    qasida_number, or pass a canonical bayt stable_id. Parallel candidates are
    explicitly labelled unverified and never presented as citation-safe.

    Set context_mode="paragraph" to request the complete source paragraph
    containing the match. If it exceeds max_chars, the response declares the
    safety cap and returns a bounded excerpt containing the evidence. Passing
    qasida_number always requests the complete structured qaṣīda.
    """
    context_chars = max(200, min(context_chars, 2000))
    if sum([match_id is not None, match_ids is not None, stable_id is not None, qasida_number is not None]) != 1:
        raise ValueError("Provide exactly one passage selector: match_id, match_ids, stable_id, or qasida_number")
    if match_ids is not None and not 1 <= len(match_ids) <= 20:
        raise ValueError("match_ids must contain between 1 and 20 IDs")
    if qasida_number is not None:
        result = db.get_qasida(int(qasida_number))
        return result or {"error": f"no qasida {qasida_number} in b14"}
    if stable_id:
        result = db.get_bayt(
            stable_id, context_chars=context_chars, context_mode=context_mode,
            max_chars=max_chars,
        )
        if result is None:
            return {"error": f"invalid or unknown stable_id '{stable_id}'"}
        if include_parallels:
            result["parallel_candidates"] = db.get_parallel_candidates(
                stable_id, limit=parallel_limit,
            )
            result["parallel_warning"] = (
                "Discovery candidates only; review_status and citation_safe are authoritative."
            )
        return result
    if match_ids:
        results = []
        for item in match_ids[:20]:
            match = db._MATCH_ID_RE.fullmatch(item or "")
            result = (db.get_passage(match.group(1), int(match.group(2)), query=query,
                      context_chars=context_chars, match_start=int(match.group(3)),
                      context_mode=context_mode, max_chars=max_chars)
                      if match else None)
            results.append(result or {"error": f"invalid or unknown match_id '{item}'"})
        return {"returned_count": len(results), "results": results}
    if not match_id:
        return {"error": "match_id, match_ids, stable_id, or qasida_number is required"}
    if query:
        match = db._MATCH_ID_RE.fullmatch(match_id or "")
        result = (db.get_passage(match.group(1), int(match.group(2)), query=query,
                                 context_chars=context_chars,
                                 match_start=int(match.group(3)),
                                 context_mode=context_mode,
                                 max_chars=max_chars) if match else None)
    else:
        result = db.get_passage_by_match_id(
            match_id, context_chars, context_mode=context_mode,
            max_chars=max_chars,
        )
    if result is None:
        return {"error": f"invalid or unknown match_id '{match_id}'"}
    if include_parallels and result.get("stable_id"):
        result["parallel_candidates"] = db.get_parallel_candidates(
            result["stable_id"], limit=parallel_limit,
        )
        result["parallel_warning"] = (
            "Discovery candidates only; review_status and citation_safe are authoritative."
        )
    return result


def _explicit_count_details(
    *, stats: dict, raw_queries: list[str], effective_match_mode: str,
    rows: list[dict], offset: int, has_more: bool, book_ids=None,
    source_code=None, page_from=None, page_to=None, qasida_number=None,
    min_tier=None, whole_word: bool = True, operator: str = "OR",
) -> dict[str, Any]:
    """Separate the retrieval result count from the literal source census."""
    count_args = dict(
        book_ids=book_ids, source_code=source_code,
        page_from=page_from, page_to=page_to,
        qasida_number=qasida_number, min_tier=min_tier,
        whole_word=whole_word,
    )
    literal = (
        stats if stats["count_basis"] == "phrase"
        else db.search_stats(
            raw_queries, operator=operator, count_basis="phrase", **count_args,
        )
    )
    relation = "article_normalized_phrase"
    scope = "matching_pages_before_ranking_and_score_filter"
    if effective_match_mode == "exact":
        retrieval_count = literal["matching_pages"]
    elif effective_match_mode == "terms":
        retrieval_count = db.search_stats(
            raw_queries, operator=operator, count_basis="term_bag", **count_args,
        )["matching_pages"]
    elif effective_match_mode == "reformulated":
        retrieval_count = offset + len(rows) if rows else 0
        relation = "lower_bound"
        scope = "eligible_candidates_after_intent_and_score_filter"
    elif effective_match_mode == "lexeme":
        lexeme_rows = db.search(
            queries=raw_queries, operator=operator, search_mode="lexeme",
            ranking="book_order", diversify_books=False, limit=10000,
            offset=0, min_score=0.0, **count_args,
        )
        retrieval_count = len({(row["book_id"], row["seq"]) for row in lexeme_rows})
        scope = "lexeme_matching_pages_before_ranking_and_score_filter"
    else:
        # Hybrid and semantic retrieval apply a calibrated evidence threshold.
        # The search path intentionally fetches only one page beyond the
        # requested limit, so label that bounded count honestly.
        retrieval_count = offset + len(rows) if rows else 0
        relation = "lower_bound"
        scope = "eligible_ranked_pages_after_score_filter"
    return {
        "retrieval_hit_count": int(retrieval_count),
        "retrieval_hit_count_relation": relation,
        "retrieval_hit_count_scope": scope,
        "literal_matching_pages": int(literal["surface_matching_pages"]),
        "literal_occurrences": int(literal["surface_occurrences"]),
        "normalized_matching_pages": int(literal["matching_pages"]),
        "normalized_occurrences": int(literal["matching_occurrences"]),
        "census_matching_pages": int(stats["matching_pages"]),
        "census_occurrences": int(stats["matching_occurrences"]),
    }


@mcp.tool(structured_output=True, meta=TOOL_META)
@safe_tool_call
@navigation_scope
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
    check_completeness: bool = False,
    include_toc: bool = False,
    include_topic_only: bool = False,
    count_basis: CountBasis = "phrase",
    whole_word: bool = True,
    min_score: float = 0.0,
    min_tier: Optional[int] = None,
    qasida_number: Optional[int] = None,
    expand_top: int = 0,
    expand_chars: int = 600,
    detail: Literal["summary", "full"] = "summary",
    keep_terms: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Search the Al Burhania Library.

    include_toc opts into navigation text; default results and counts exclude it.
    include_topic_only includes weak question candidates for exploration.
    Question relations are local anchor checks, never verified answers.

    Typical workflow:
    1. search_library
    2. get_passage for the precise passage identified by a result
    3. get_page only when broader page context is required

    The complete toolset is exactly: search_library, get_passage, get_page,
    get_book, and list_books.

    Citation metadata is explicit: citation_label is universal; Dīwān
    bayt_from/bayt_to are page-scoped and qasida_bayt_count is the complete
    qaṣīda length. A heading hit has a stable qasida-heading identifier rather
    than being misrepresented as bayt 1. TOC/fihris pages declare block_type=toc.

    Args:
        query: One Arabic word or phrase.
        queries: Optional alternatives in one request. When supplied, this
            takes precedence over query.
        operator: Combine alternatives with OR (default) or AND.
        limit: Number of results. Defaults to 8 and is capped at 20.
        offset: Zero-based pagination offset.
        book_ids: Optional book IDs to search, such as ["b33"]. Ordinary
            whole-library search excludes editions marked
            searchable_by_default=false so repeated editions do not duplicate
            results or counts. Passing that edition's ID explicitly searches
            it and preserves its own printed-page citations.
        book_scope: Optional title/series fragment, such as "شرح شراب الوصل".
        source_code: Optional "primary" or "secondary" filter.
        min_tier: Minimum accepted authority expressed as the largest numeric
            tier allowed. For example, min_tier=2 restricts results to tiers
            1–2. Values are 1–5.
        page_from: Optional first page sequence, inclusive.
        page_to: Optional last page sequence, inclusive.
        context_chars: Context on each side of the match. Defaults to 60 and
            is restricted to 40–300.
        mode: compact or ultra_compact. When expand_top is requested,
            compact returns expanded_passage and ultra_compact returns the
            same bounded passage object under the abbreviated key ep.
            Contract 14 aliases are reversible using the published decoder map
            in contract metadata. Source spans address canonical get_page.text.
            Candidate support is uncalibrated and never verifies an answer.
            Ultra-compact search hits expose citation_label as c and
            block_type as blk (body or toc). The key bt remains bayt_to.
        match_mode: auto, exact, terms, hybrid, or lexeme. When a local
            semantic index is present, auto unions exact, terms, lexeme and
            semantic candidates and reranks them. Otherwise it falls back to
            exact, terms, then lexical hybrid. Every hit declares match_type. Lexeme
            accepts one Arabic word per query and expands common proclitics,
            suffixes, and weak-final ي/ا forms for recall-oriented census work.
            Every hit includes rank, score, and score_kind. Scores are stable
            evidence measures rather than reciprocal rank: bounded BM25 for
            exact/lexeme, proximity plus BM25 for terms, fixed evidence fusion
            for hybrid, and cosine/fusion scores for semantic auto retrieval.
            Higher means stronger evidence under the declared score_kind.
        search_mode: Legacy alias. With match_mode=auto it selects the explicit
            legacy mode. Contradictory explicit selectors are rejected.
        whole_word: Defaults true. Exact/terms/count evidence is token-anchored;
            short words such as سر and لا never match inside longer tokens.
        count_basis: phrase (default) or term_bag. This determines counts
            independently of match_mode, and is always returned with the census.
            Count responses distinguish retrieval_hit_count from
            literal_matching_pages and literal_occurrences.
        check_completeness: Audit actual eligible lexical candidates before
            ranking/score filtering/pagination, independently of counts.
            include_counts also enables this audit. Other retrieval modes
            explicitly report not_checked or not_supported, never implied success.
        min_score: Filter by the declared evidence score before pagination.
            Exact textual presence is independent of BM25 magnitude: a common
            literal hit can legitimately have score 0.0. Leave this at 0.0 for
            exact occurrence censuses and decide literal presence from the
            returned evidence, match_type, and matched_terms.
            It never acts as a disguised result-rank cutoff.
        ranking: relevance, primary_first, chronological, or book_order.
            primary_first uses a bounded authority adjustment: a primary
            source and a stronger source tier win when relevance is comparable,
            but they do not override a substantial relevance gap. The lexical
            evidence score remains separate from the authority-adjusted
            rank_score.
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
    if min_tier is not None and not 1 <= int(min_tier) <= 5:
        return {"error": "min_tier must be between 1 and 5"}

    if book_scope:
        scoped_ids = db.resolve_book_scope(book_scope)
        if not scoped_ids:
            return {"error": f"no books match scope '{book_scope}'"}
        book_ids = sorted(set(book_ids or scoped_ids) & set(scoped_ids)) if book_ids else scoped_ids
        if not book_ids:
            return {"error": "book_ids and book_scope do not overlap"}

    aliases = {"exact_phrase": "exact", "all_words": "terms", "any_word": "terms", "lexeme": "lexeme"}
    if search_mode is not None:
        if match_mode != "auto" and match_mode != aliases[search_mode]:
            raise ValueError("search_mode conflicts with match_mode; use one mode selector")
        match_mode = aliases[search_mode]

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
    audit_requested = bool(include_counts or check_completeness)
    if include_counts:
        stats = db.search_stats(
            raw_queries, operator=operator, book_ids=book_ids,
            source_code=source_code, page_from=page_from, page_to=page_to,
            qasida_number=qasida_number, min_tier=min_tier,
            count_basis=count_basis, whole_word=whole_word,
        )
        total_hits = stats["matching_pages"]

    effective_match_mode = match_mode
    from app.services.question_intent import is_question, plan
    question_mode = match_mode == "auto" and any(is_question(q) for q in raw_queries)
    if question_mode:
        effective_match_mode = "reformulated"
        from app.services.question_search import search_questions
        rows = search_questions(query=query, queries=raw_queries, operator=operator, keep_terms=keep_terms,
            ranking=ranking, book_ids=book_ids, source_code=source_code,
            page_from=page_from, page_to=page_to, limit=limit+1, offset=offset,
            context_chars=context_chars, diversify_books=diversify_books,
            max_per_book=max_per_book, qasida_number=qasida_number, min_tier=min_tier,
            whole_word=whole_word, min_score=min_score, include_topic_only=include_topic_only)
    if match_mode == "auto" and not question_mode:
        from app.services import semantic_search as semantic
        rows = []
        if semantic.semantic_available():
            rows = semantic.auto_search(
                query=query, queries=raw_queries, operator=operator,
                search_mode=resolved_search_mode, ranking=ranking,
                book_ids=book_ids, source_code=source_code,
                page_from=page_from, page_to=page_to, limit=limit + 1,
                offset=offset, context_chars=context_chars,
                diversify_books=diversify_books, max_per_book=max_per_book,
                qasida_number=qasida_number, min_score=min_score,
                min_tier=min_tier, whole_word=whole_word,
            )
            if rows:
                effective_match_mode = "semantic_auto"
        # A semantic index is never allowed to turn a lexical fallback into a
        # silent zero. If fusion returns nothing, run the same deterministic
        # lexical cascade used when vectors are absent.
        if not rows:
            cascade = (("exact", "exact_phrase", db.search),
                       ("terms", "all_words", db.search),
                       ("hybrid", "all_words", db.hybrid_search))
            from app.core.arabic_utils import safe_tokens
            if all(len(safe_tokens(q))<=3 for q in raw_queries):cascade=cascade[:2]
            for effective_match_mode, resolved_search_mode, candidate_fn in cascade:
                probe = dict(query=query, queries=raw_queries, operator=operator,
                             search_mode=resolved_search_mode, ranking=ranking,
                             book_ids=book_ids, source_code=source_code,
                             page_from=page_from, page_to=page_to, limit=limit + 1,
                             offset=offset, context_chars=context_chars,
                             diversify_books=diversify_books, max_per_book=max_per_book,
                             qasida_number=qasida_number, min_tier=min_tier,
                             whole_word=whole_word)
                probe["min_score"] = min_score
                probe["_audit_candidates"] = audit_requested
                rows = candidate_fn(**probe)
                if rows:
                    break
        if not rows:
            effective_match_mode = "reformulated"
            from app.services.question_search import search_questions
            rows = search_questions(
                query=query, queries=raw_queries, operator=operator,
                ranking=ranking, book_ids=book_ids, source_code=source_code,
                page_from=page_from, page_to=page_to, limit=limit + 1,
                offset=offset, context_chars=context_chars,
                diversify_books=diversify_books, max_per_book=max_per_book,
                qasida_number=qasida_number, min_tier=min_tier,
                whole_word=whole_word, min_score=min_score,
            )
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
        min_tier=min_tier,
        whole_word=whole_word,
    )
    search_args["min_score"] = min_score
    search_args["_audit_candidates"] = audit_requested
    if match_mode != "auto":
        rows = search_fn(**search_args)

    from app.services.hit_contract import canonical_hit
    rows=[canonical_hit(row,db.get_page(row['book_id'],row['seq'])) for row in rows]
    has_more = len(rows) > limit
    results = rows[:limit]
    count_details = None
    if include_counts:
        count_details = _explicit_count_details(
            stats=stats, raw_queries=raw_queries,
            effective_match_mode=effective_match_mode, rows=rows,
            offset=offset, has_more=has_more, book_ids=book_ids,
            source_code=source_code, page_from=page_from, page_to=page_to,
            qasida_number=qasida_number, min_tier=min_tier,
            whole_word=whole_word, operator=operator,
        )
    completeness = {"status": "not_checked", "reason": "Request check_completeness=true or include_counts=true"}
    if audit_requested and effective_match_mode in {"exact", "terms", "lexeme"}:
        completeness = db.retrieval_completeness(
            raw_queries, resolved_search_mode, operator=operator,
            candidate_ids=candidate_snapshot() if candidate_snapshot() is not None else set(),
            per_query_candidates=query_candidate_snapshot(),
            whole_word=whole_word, book_ids=book_ids, source_code=source_code,
            page_from=page_from, page_to=page_to, qasida_number=qasida_number,
            min_tier=min_tier,
        )

    elif audit_requested and effective_match_mode == "hybrid" and candidate_snapshot() is not None:
        scope = dict(book_ids=book_ids, source_code=source_code, page_from=page_from,
                     page_to=page_to, qasida_number=qasida_number, min_tier=min_tier)
        completeness = db.literal_inclusion_report(raw_queries, candidate_snapshot(),
            operator=operator, whole_word=whole_word, **scope)
        completeness["per_query"] = [{"query": q, **db.literal_inclusion_report(
            [q], candidate_snapshot(), whole_word=whole_word, **scope)} for q in raw_queries]
        completeness["per_query_scope"] = "inclusion_in_combined_candidate_union"
        completeness["method"] = "actual_retrieved_candidates"
        if operator == "AND":
            completeness["per_query"] = [{"query": q, **db.literal_inclusion_report(
                raw_queries, candidate_snapshot(), operator="AND", whole_word=whole_word, **scope)} for q in raw_queries]
            completeness["per_query_scope"] = "combined_AND_eligibility"
        if any(item["status"] == "warning" for item in completeness["per_query"]):
            completeness["status"] = "warning"
    elif audit_requested:
        completeness = {"status": "not_supported", "reason": "Literal inclusion is not a completeness metric for reformulated or semantic discovery", "effective_match_mode": effective_match_mode}

    expand_top = max(0, min(expand_top, len(results)))
    expand_chars = max(200, min(expand_chars, 2000))
    attach_expanded_passages(
        results,
        expand_top=expand_top,
        expand_chars=expand_chars,
        passage_loader=db.get_passage_by_match_id,
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
        if count_details:
            payload.update(count_details)
            payload["census_version"] = {"server_version":TOOL_META["server_version"],"navigation_scope":"body_and_toc" if include_toc else "body_only"}
        if (
            include_counts and total_hits == 0 and len(raw_queries) == 1
            and qasida_number is None
        ):
            suggestions = db.suggest_spelling(raw_queries[0])
            if suggestions:
                payload["suggestions"] = suggestions
        if include_counts and min_score > 0.0:
            payload["census_count_scope"] = "lexical_matches_before_score_filter"
        payload["navigation_scope"] = "body_and_toc" if include_toc else "body_only"
        payload["reformulation_status"] = "not_needed"
        if effective_match_mode=="reformulated":
            from app.services.question_search import SEARCH_STATE
            payload.update(SEARCH_STATE.get() or {})
            payload['reformulation_status']='degraded' if (payload.get('completion')=='partial' or payload.get('stages_skipped')) else 'ok'
            from app.services.question_search import anchor_plan
            payload["query_plan"] = [{"original_query":q, **anchor_plan(q,keep_terms or ())} for q in raw_queries]
            payload["dropped_function_words"] = list(dict.fromkeys(t for p in payload["query_plan"] for t in p["dropped_function_words"]))
            payload["answer_verified"] = False
        from app.services.evidence_units import INDEX_VERSION
        from app.services.concept_links import VERSION as LEXICON_VERSION
        from app.services.intent_frames import VERSION as FRAME_VERSION
        payload['versions']={'index':INDEX_VERSION,'lexicon':LEXICON_VERSION,'cues':FRAME_VERSION,'ranker':'source-rules-fusion-1'}
        payload["ranking_policy"] = db.ranking_policy(ranking)
        payload["effective_match_mode"] = effective_match_mode
        payload["whole_word"] = bool(whole_word)
        if len(results)<limit and not has_more:
            payload["fewer_than_limit_reason"] = "only_n_passages_met_threshold"
        payload["normalization_level"] = (
            "broad_discovery" if effective_match_mode in {"hybrid", "lexeme", "reformulated", "semantic_auto"}
            else "safe"
        )
        if not results:
            payload["diagnostics"] = db.zero_result_diagnostics(
                raw_queries,
                attempted_modes=(
                    (["subject_phrase", "passage_terms", "reformulated"] if question_mode else ["exact", "terms", "hybrid", "reformulated"])
                    if match_mode == "auto" else [effective_match_mode]
                ),
                book_ids=book_ids, source_code=source_code,
                page_from=page_from, page_to=page_to,
                qasida_number=qasida_number, min_tier=min_tier,
                whole_word=whole_word, min_score=min_score, offset=offset,
                include_topic_only=include_topic_only, operator=operator,
            )
        if completeness:
            payload["retrieval_completeness"] = completeness
            if completeness["status"] == "warning":
                payload.setdefault("diagnostics", {}).update({
                    "literal_inclusion_warning": True,
                    "message": "Eligible literal pages are missing before pagination; inspect retrieval_completeness.",
                })
        from app.services.compact_response import slim_response
        return slim_response(payload,detail=detail,ultra=mode=="ultra_compact")

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
        "min_tier": min_tier,
        "whole_word": bool(whole_word),
        "normalization_level": (
            "broad_discovery" if effective_match_mode in {"hybrid", "lexeme", "reformulated", "semantic_auto"}
            else "safe"
        ),
        "returned_count": len(results),
        "offset": offset,
        "next_offset": offset + limit if has_more else None,
        "primary_hits": primary_hits,
        "secondary_hits": len(results) - primary_hits,
        "provenance": _GRADE_REMINDER,
        "results": results,
    }
    if include_counts:
        response.update(count_details or {})
        if min_score > 0.0:
            response["census_count_scope"] = "lexical_matches_before_score_filter"
        response["count_basis"] = stats["count_basis"]
        response["count_semantics"] = stats
        response["per_query"] = stats["per_query"]
    if not results:
        response["diagnostics"] = db.zero_result_diagnostics(
            raw_queries,
            attempted_modes=(
                ["exact", "terms", "hybrid", "reformulated"]
                if match_mode == "auto" else [effective_match_mode]
            ),
            book_ids=book_ids, source_code=source_code,
            page_from=page_from, page_to=page_to,
            qasida_number=qasida_number, min_tier=min_tier,
            whole_word=whole_word,
        )
    return response


# This examines the same FastMCP registry used to answer protocol tools/list.
# A missing decorator, unexpected tool, or stale conditional registration now
# prevents the application from starting instead of silently shipping drift.
DISCOVERABLE_TOOLS = validate_registered_tools(mcp)
bind_callable_schema(mcp)
from app.core.machine_http import enable_threaded_tools
enable_threaded_tools(mcp)

app = mcp.streamable_http_app()
