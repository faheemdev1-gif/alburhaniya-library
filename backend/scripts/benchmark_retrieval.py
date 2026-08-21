#!/usr/bin/env python3
"""Repeatable quality and response-size benchmark for library retrieval."""
from __future__ import annotations
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app.services import library_db as db
from app.services.compact_response import compact_search_response


def run() -> dict:
    tests = {}
    tests["fully_vowelled_search"] = bool(db.search("اللّٰه", limit=1))
    tests["unvowelled_search"] = bool(db.search("الله", limit=1))
    tests["common_word_library"] = len(db.search("الله", limit=8)) == 8
    tests["single_book_pagination"] = len(
        db.search("الله", book_ids=["b14"], limit=8, diversify_books=True)
    ) == 8
    tests["primary_filter"] = all(x["source_code"] == "primary" for x in db.search("الله", source_code="primary", limit=5))
    tests["secondary_filter"] = all(x["source_code"] == "secondary" for x in db.search("الله", source_code="secondary", limit=5))
    hit = db.search("المريد", limit=1)[0]
    tests["page_retrieval"] = db.get_page(hit["book_id"], hit["seq"]) is not None
    tests["empty_result"] = db.search("لفظغيرموجوداطلاقا", limit=2) == []
    tests["spelling_suggestions"] = isinstance(db.suggest_spelling("المعنى"), list)
    tests["strict_terms_reject_root_relatives"] = db.search(
        "المحافظة الصلاة وقتها", search_mode="all_words", limit=5
    ) == []
    genuine_terms = db.search("المريد الشيخ", search_mode="all_words", limit=3)
    tests["terms_explain_matched_forms"] = bool(genuine_terms) and all(
        set(row.get("matched_terms", {})) == {"المريد", "الشيخ"}
        for row in genuine_terms
    )
    short_hybrid = db.hybrid_search(query="المحافظة الصلاة وقتها", limit=5)
    tests["short_hybrid_recall"] = bool(short_hybrid) and all(
        row["book_id"] == "b44" for row in short_hybrid
    )
    tests["hybrid_evidence_span"] = bool(short_hybrid) and all(
        row.get("evidence_span") and not row["match_id"].endswith("-c0")
        for row in short_hybrid
    )
    tests["hybrid_score_separation"] = (
        len(short_hybrid) >= 2
        and short_hybrid[0]["score"] - short_hybrid[1]["score"] > 0.05
    )
    tests["bad_hybrid_suppressed"] = db.hybrid_search(
        query="الصلاة خير من النوم", book_ids=["b29"], limit=5
    ) == []
    exact_article = db.search("المحافظة", search_mode="exact_phrase", limit=1)
    tests["exact_article_has_evidence_offset"] = bool(exact_article) and (
        not exact_article[0]["match_id"].endswith("-c0")
        and "<mark>محافظة</mark>" in exact_article[0]["snippet"]
    )
    exact_pruned = db.search(
        "المحافظة", search_mode="exact_phrase", limit=5, min_score=0.99,
    )
    tests["exact_min_score_prunes"] = len(exact_pruned) == 1 and (
        exact_pruned[0]["score"] >= 0.99
    )
    diwan = db.search(
        "فما طلعت إلا وغاب ضياؤها", book_ids=["b14"], limit=1
    )
    tests["diwan_stable_structural_id"] = bool(diwan) and (
        diwan[0].get("stable_id") == "b14-q091-b009"
    )
    toc = db.search(
        "مشروعية الذكر للنساء", book_ids=["b29"],
        ranking="relevance", limit=5, diversify_books=False,
    )
    tests["body_outranks_toc"] = len(toc) >= 2 and (
        toc[0]["block_type"] == "body" and toc[1]["block_type"] == "toc"
    )

    conn = db._connection()
    lengths = [r[0] for r in conn.execute("SELECT length(text) FROM pages")]
    largest = max(lengths)
    tests["large_segment_detection"] = largest > 0

    rows = db.search("الله", limit=8)
    compact = json.dumps(compact_search_response(rows, limit=8, offset=0, has_more=False), ensure_ascii=False)
    ultra = json.dumps(compact_search_response(rows, limit=8, offset=0, has_more=False, ultra=True), ensure_ascii=False)
    standard = json.dumps({"results": rows}, ensure_ascii=False)

    duplicate_rows = conn.execute("""
        SELECT COUNT(*) FROM (
          SELECT book_id, seq, COUNT(*) c FROM pages GROUP BY book_id, seq HAVING c > 1
        )
    """).fetchone()[0]
    total_pages = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    passed = sum(bool(v) for v in tests.values())
    timings = []
    for _ in range(7):
        started = time.perf_counter()
        rows = db.hybrid_search(query="المحافظة الصلاة وقتها", limit=5)
        for row in rows[:2]:
            db.get_passage_by_match_id(row["match_id"], 600)
        timings.append((time.perf_counter() - started) * 1000)
    return {
        "tests_passed": f"{passed}/{len(tests)}",
        "tests": tests,
        "largest_segment_chars": largest,
        "average_segment_chars": round(statistics.mean(lengths), 1),
        "duplicate_page_rate_percent": round((duplicate_rows / total_pages) * 100, 3),
        "response_bytes": {"standard": len(standard.encode()), "compact": len(compact.encode()), "ultra_compact": len(ultra.encode())},
        "compact_saving_percent": round((1 - len(compact) / len(standard)) * 100, 1),
        "ultra_saving_percent": round((1 - len(ultra) / len(standard)) * 100, 1),
        "hybrid_plus_two_passages_median_ms": round(statistics.median(timings), 2),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
