"""Local, filter-aware semantic retrieval over memory-mapped E5 vectors."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from html import escape as _esc
from typing import Iterable

import numpy as np

from app.core.arabic_utils import normalize_arabic, normalized_tokens
from app.core.config import get_settings


def _setting(name: str, default):
    return getattr(get_settings(), name, default)


@lru_cache(maxsize=1)
def _load_index() -> tuple[np.ndarray, dict]:
    vectors_path = _setting("semantic_embeddings_path", "semantic_embeddings.npy")
    manifest_path = _setting("semantic_manifest_path", "semantic_manifest.json")
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    vectors = np.load(vectors_path, mmap_mode="r")
    if vectors.ndim != 2:
        raise RuntimeError("semantic embedding matrix must be two-dimensional")
    if int(manifest.get("chunk_count", -1)) != vectors.shape[0]:
        raise RuntimeError("semantic manifest chunk_count does not match vectors")
    if int(manifest.get("dimensions", -1)) != vectors.shape[1]:
        raise RuntimeError("semantic manifest dimensions do not match vectors")
    return vectors, manifest


def semantic_available() -> bool:
    if not _setting("enable_local_semantic_search", True):
        return False
    vectors_path = _setting("semantic_embeddings_path", "semantic_embeddings.npy")
    manifest_path = _setting("semantic_manifest_path", "semantic_manifest.json")
    if not (os.path.exists(vectors_path) and os.path.exists(manifest_path)):
        return False
    try:
        from app.services import library_db as db
        row = db._connection().execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='semantic_chunks'"
        ).fetchone()
        return bool(row)
    except Exception:
        return False


def _top_indices(scores: np.ndarray, limit: int) -> np.ndarray:
    """Descending top-k indices, including safe handling for small filters."""
    count = int(scores.shape[0])
    k = min(max(0, int(limit)), count)
    if k == 0:
        return np.empty(0, dtype=np.int64)
    if k == count:
        return np.argsort(scores)[::-1]
    selected = np.argpartition(scores, count - k)[count - k:]
    return selected[np.argsort(scores[selected])[::-1]]


def _optional_field(row, key: str):
    """Read optional metadata from sqlite rows or test dictionaries."""
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def _candidate_rows(
    *, book_ids: list[str] | None, source_code: str | None,
    page_from: int | None, page_to: int | None, qasida_number: int | None,
) -> list:
    from app.services import library_db as db

    where, params = [], []
    if book_ids:
        where.append("c.book_id IN (" + ",".join("?" for _ in book_ids) + ")")
        params.extend(book_ids)
    if source_code:
        where.append("b.source_code = ?")
        params.append(source_code)
    if page_from is not None:
        where.append("c.seq >= ?")
        params.append(page_from)
    if page_to is not None:
        where.append("c.seq <= ?")
        params.append(page_to)
    if qasida_number is not None:
        where.append("c.qasida_number = ?")
        params.append(qasida_number)
    clause = " WHERE " + " AND ".join(where) if where else ""
    return db._connection().execute(
        """SELECT c.*, b.title AS book_title, b.source_grade, b.source_code
             FROM semantic_chunks c
             JOIN books b ON b.book_id = c.book_id""" + clause +
        " ORDER BY c.vector_index",
        params,
    ).fetchall()


def semantic_search(
    query: str,
    *,
    book_ids: list[str] | None = None,
    source_code: str | None = None,
    page_from: int | None = None,
    page_to: int | None = None,
    qasida_number: int | None = None,
    limit: int = 40,
    context_chars: int = 60,
    min_score: float | None = None,
) -> list[dict]:
    """Return filtered semantic candidates as normal library search rows."""
    if not semantic_available():
        return []
    vectors, manifest = _load_index()
    model_name = str(manifest["model"])
    from app.services.embeddings import get_embedding_service

    normalized_query = normalize_arabic(query, aggressive=False).strip()
    query_vector = np.asarray(
        get_embedding_service(model_name).embed_query(normalized_query),
        dtype=np.float32,
    )
    if query_vector.shape != (vectors.shape[1],):
        raise RuntimeError("query embedding dimensions do not match semantic index")

    rows = _candidate_rows(
        book_ids=book_ids, source_code=source_code,
        page_from=page_from, page_to=page_to, qasida_number=qasida_number,
    )
    if not rows:
        return []
    vector_indices = np.fromiter(
        (int(row["vector_index"]) for row in rows), dtype=np.int64
    )
    scores = np.asarray(vectors[vector_indices], dtype=np.float32) @ query_vector
    threshold = (
        float(min_score) if min_score is not None
        else float(_setting("semantic_min_score", 0.0))
    )
    selected = _top_indices(scores, limit)
    results = []
    excerpt_chars = max(40, min(int(context_chars), 300)) * 2
    for rank, local_index in enumerate(selected, start=1):
        raw_score = float(scores[local_index])
        if raw_score < threshold:
            continue
        row = rows[int(local_index)]
        text = row["text"]
        snippet = _esc(text[:excerpt_chars])
        if len(text) > excerpt_chars:
            snippet += "…"
        bounded_score = max(0.0, min(1.0, raw_score))
        result = {
            "book_id": row["book_id"], "book_title": row["book_title"],
            "source_grade": row["source_grade"], "source_code": row["source_code"],
            "source_tier": row["source_tier"], "seq": row["seq"],
            "page_number": row["seq"],
            "page_label": (f"الصفحة {row['printed_page']}" if row["printed_page"]
                           else f"المقطع {row['seq']}"),
            "printed_page": row["printed_page"],
            "citation_label": row["citation_label"],
            "qasida_number": row["qasida_number"],
            "qasida_title": row["qasida_title"],
            "qasida_bayt_count": _optional_field(row, "qasida_bayt_count"),
            "bayt_from": row["bayt_from"], "bayt_to": row["bayt_to"],
            "page_bayt_from": row["bayt_from"],
            "page_bayt_to": row["bayt_to"],
            "bayt_range_scope": "page" if row["bayt_from"] is not None else None,
            "snippet": snippet, "match_id": row["chunk_id"],
            "match_type": "semantic", "score": round(bounded_score, 6),
            "score_kind": "semantic_cosine", "rank": rank,
            "semantic_score": round(raw_score, 6),
            "citation_verified": False, "verification_required": True,
        }
        if row["book_id"] == "b14" and row["qasida_number"] is not None:
            result["container_id"] = f"b14-q{int(row['qasida_number']):03d}"
        results.append(result)
    return results


def _coverage(query: str, text: str) -> float:
    terms = normalized_tokens(query, drop_stopwords=True)
    if not terms:
        return 0.0
    normalized = normalize_arabic(text, aggressive=True)
    return sum(1 for term in terms if term in normalized) / len(terms)


def combine_candidates(
    query: str,
    lexical_groups: Iterable[tuple[str, list[dict]]],
    semantic_rows: list[dict],
) -> list[dict]:
    """Fuse page-level candidates while keeping semantic-only hits unverified."""
    candidates: dict[tuple[str, int], dict] = {}
    lexical_priority = {"exact": 3, "terms": 2, "lexeme": 1, "hybrid": 1}

    for match_type, rows in lexical_groups:
        for row in rows:
            key = (row["book_id"], row["seq"])
            item = candidates.setdefault(key, {
                "row": row, "lexical_score": 0.0, "semantic_score": 0.0,
                "exact": False,
            })
            if lexical_priority.get(match_type, 0) > lexical_priority.get(
                item["row"].get("match_type"), 0
            ):
                item["row"] = row
            item["lexical_score"] = max(item["lexical_score"], float(row["score"]))
            item["exact"] = item["exact"] or match_type == "exact"

    for row in semantic_rows:
        key = (row["book_id"], row["seq"])
        item = candidates.setdefault(key, {
            "row": row, "lexical_score": 0.0, "semantic_score": 0.0,
            "exact": False,
        })
        if float(row["semantic_score"]) > item["semantic_score"]:
            item["semantic_score"] = float(row["semantic_score"])
            if not item["lexical_score"]:
                item["row"] = row

    ranked = []
    for item in candidates.values():
        row = dict(item["row"])
        quality = _coverage(query, row.get("snippet", ""))
        semantic = item["semantic_score"]
        lexical = item["lexical_score"]
        if item["exact"]:
            final = 0.60 * lexical + 0.30 * semantic + 0.10 * quality
        else:
            final = 0.55 * semantic + 0.35 * lexical + 0.10 * quality
        row["_combined_score"] = max(0.0, final)
        if semantic:
            row["semantic_score"] = round(semantic, 6)
        if row.get("match_type") != "semantic":
            row["citation_verified"] = True
            row["verification_required"] = False
        ranked.append(row)

    ranked.sort(key=lambda row: (
        -row["_combined_score"], row["source_tier"], row["book_id"], row["seq"]
    ))
    for row in ranked:
        row["score"] = round(min(1.0, row.pop("_combined_score")), 6)
        row["score_kind"] = "auto_fusion"
    return ranked


def auto_search(**kwargs) -> list[dict]:
    """Exact + terms + lexeme + semantic candidate union and reranking."""
    from app.services import library_db as db

    raw_queries = kwargs.get("queries") or ([kwargs.get("query")] if kwargs.get("query") else [])
    combined_query = " ".join(q for q in raw_queries if q)
    limit = int(kwargs.get("limit", 10))
    offset = int(kwargs.get("offset", 0))
    pool = min(max((offset + limit) * 6, 40), 200)
    base = dict(kwargs)
    base.update(limit=pool, offset=0, diversify_books=False)
    base.pop("min_score", None)

    groups = []
    for match_type, mode in (("exact", "exact_phrase"), ("terms", "all_words")):
        call = dict(base, search_mode=mode)
        groups.append((match_type, db.search(**call)))
    if len(normalized_tokens(combined_query)) == 1:
        groups.append(("lexeme", db.search(**dict(base, search_mode="lexeme"))))

    semantic_rows = semantic_search(
        combined_query,
        book_ids=kwargs.get("book_ids"), source_code=kwargs.get("source_code"),
        page_from=kwargs.get("page_from"), page_to=kwargs.get("page_to"),
        qasida_number=kwargs.get("qasida_number"), limit=pool,
        context_chars=kwargs.get("context_chars", 60),
        min_score=0.0,
    )
    rows = combine_candidates(combined_query, groups, semantic_rows)

    if kwargs.get("ranking") in {"book_order", "chronological"}:
        rows.sort(key=lambda row: (row["book_id"], row["seq"]))
    elif kwargs.get("ranking") == "primary_first":
        rows.sort(key=db.primary_first_sort_key)

    if kwargs.get("diversify_books", True) and not (
        kwargs.get("book_ids") and len(kwargs["book_ids"]) == 1
    ):
        max_per_book = max(1, int(kwargs.get("max_per_book", 2)))
        counts, diversified = {}, []
        for row in rows:
            count = counts.get(row["book_id"], 0)
            if count < max_per_book:
                diversified.append(row)
                counts[row["book_id"]] = count + 1
        rows = diversified
    requested_min = max(0.0, min(float(kwargs.get("min_score") or 0.0), 1.0))
    if requested_min > 0.0:
        rows = [row for row in rows if row["score"] >= requested_min]
    page = rows[offset: offset + limit]
    for rank, row in enumerate(page, start=offset + 1):
        row["rank"] = rank
    return page
