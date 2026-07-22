"""
Search service.

By default this does PURE exact/keyword matching via Meilisearch — no
semantic/meaning-based matching. A word is searched literally, and every
page across the library that contains it is returned, grouped one card
per page (a page can contain the word several times across its indexed
chunks — those are merged into a single result with an occurrence count).

The old semantic (Qdrant + embeddings) code path is left in place but
disabled. Flip `enable_semantic_search = True` in core/config.py to bring
back the previous hybrid keyword+semantic behaviour.
"""
from __future__ import annotations
import re
from app.core.config import get_settings
from app.core.arabic_utils import normalize_arabic
from app.services import keyword_search as kw

_MARK_RE = re.compile(r"<mark>", re.IGNORECASE)


def _rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank + 1)


def _count_occurrences(highlighted_html: str) -> int:
    """Count how many times the query was highlighted in a snippet."""
    return len(_MARK_RE.findall(highlighted_html or ""))


def _keyword_search_grouped_by_page(
    query: str,
    book_ids: list[str] | None,
    limit: int,
) -> list[dict]:
    """
    Exact keyword search, with all matching chunks on the same book page
    merged into a single result card (one card per page).
    """
    hits = kw.keyword_search(query, book_ids=book_ids, limit=limit)

    pages: dict[tuple[str, int], dict] = {}
    for hit in hits:
        key = (hit["book_id"], hit["page_number"])
        highlight = hit.get("_formatted", {}).get("text", hit["text"])
        occ = _count_occurrences(highlight)

        existing = pages.get(key)
        if existing is None:
            pages[key] = {
                "chunk_id":    hit["id"],
                "book_id":     hit["book_id"],
                "book_title":  hit["book_title"],
                "page_number": hit["page_number"],
                "page_label":  hit.get("page_label", hit["page_number"]),
                "chunk_index": hit.get("chunk_index", 0),
                "text":        hit["text"],
                "highlight":   highlight,
                "occurrences": occ,
            }
        else:
            # Same page, another matching chunk (chunks overlap by design,
            # so this also happens for pages that were split into several
            # chunks) — merge the occurrence count and keep whichever
            # snippet has the most matches as the representative preview.
            existing["occurrences"] += occ
            if occ > _count_occurrences(existing["highlight"]):
                existing["text"] = hit["text"]
                existing["highlight"] = highlight

    results = list(pages.values())
    # Group by book, then walk forward page by page — the natural way to
    # scan "every place this word appears" across the library.
    results.sort(key=lambda r: (r["book_title"], r["page_number"]))
    return results


def hybrid_search(
    query: str,
    book_ids: list[str] | None = None,
    limit: int = 2000,
) -> list[dict]:
    s = get_settings()
    norm_query = normalize_arabic(query, aggressive=True)

    if not s.enable_semantic_search:
        return _keyword_search_grouped_by_page(norm_query, book_ids, limit)

    # ── Legacy hybrid path (keyword + semantic via RRF) ─────────────────────
    # Kept intact and dormant — only runs if enable_semantic_search is
    # switched back on in config.py.
    from app.services import vector_search as vs
    from app.services.embeddings import get_embedding_service

    kw_hits = kw.keyword_search(norm_query, book_ids=book_ids, limit=limit)

    emb_svc = get_embedding_service(s.embedding_model)
    q_vec = emb_svc.embed_one(norm_query)
    sem_hits = vs.semantic_search(q_vec, book_ids=book_ids, limit=limit)

    scores: dict[str, float] = {}
    meta:   dict[str, dict]  = {}

    for rank, hit in enumerate(kw_hits):
        cid = hit["id"]
        scores[cid] = scores.get(cid, 0) + s.hybrid_keyword_weight * _rrf_score(rank)
        meta[cid] = {
            "chunk_id":    cid,
            "book_id":     hit["book_id"],
            "book_title":  hit["book_title"],
            "page_number": hit["page_number"],
            "page_label":  hit.get("page_label", hit["page_number"]),
            "chunk_index": hit.get("chunk_index", 0),
            "text":        hit["text"],
            "highlight":   hit.get("_formatted", {}).get("text", hit["text"]),
        }

    for rank, hit in enumerate(sem_hits):
        cid = hit["chunk_id"]
        scores[cid] = scores.get(cid, 0) + s.hybrid_semantic_weight * _rrf_score(rank)
        if cid not in meta:
            meta[cid] = {
                "chunk_id":    cid,
                "book_id":     hit["book_id"],
                "book_title":  hit["book_title"],
                "page_number": hit["page_number"],
                "page_label":  hit.get("page_label", hit["page_number"]),
                "chunk_index": hit.get("chunk_index", 0),
                "text":        hit["text"],
                "highlight":   hit["text"],
            }

    ranked = sorted(scores.keys(), key=lambda c: scores[c], reverse=True)[:limit]
    return [
        {**meta[c], "score": round(scores[c], 4)}
        for c in ranked
    ]
