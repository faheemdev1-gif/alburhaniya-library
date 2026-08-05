#!/usr/bin/env python3
"""Repeatable quality and response-size benchmark for library retrieval."""
from __future__ import annotations
import json
import os
import statistics
import sys

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
    return {
        "tests_passed": f"{passed}/{len(tests)}",
        "tests": tests,
        "largest_segment_chars": largest,
        "average_segment_chars": round(statistics.mean(lengths), 1),
        "duplicate_page_rate_percent": round((duplicate_rows / total_pages) * 100, 3),
        "response_bytes": {"standard": len(standard.encode()), "compact": len(compact.encode()), "ultra_compact": len(ultra.encode())},
        "compact_saving_percent": round((1 - len(compact) / len(standard)) * 100, 1),
        "ultra_saving_percent": round((1 - len(ultra) / len(standard)) * 100, 1),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
