#!/usr/bin/env python3
"""Independent CI audit of stable IDs, ordinals, counts, and TOC placement.

This deliberately does not import the server's corpus-contract implementation.
It gives CI a second code path for checking claims exposed by ``/health``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path


EXPECTED = {
    "books": 43,
    "pages": 6935,
    "qasidas": 95,
    "bayts": 2682,
    "default_search_books": 42,
    "default_search_pages": 6885,
    "ordinal_digest": "c354110999fb08d95a8d8d090fa63cc9eb47ddb62e4ea77e25b7261b66676a8d",
}
QASIDA_HEADING = re.compile(
    r"الْ?قَ?صِ?يدَ?ة\s+([^:\n]{1,80}):\s*([^\n]+?)"
    r"(?=\s+التّ?اريخ\s*:)"
)
# OCR/source extraction may join ``فهرس الجزء`` as ``فهرس الجزء`` or
# ``فهرس الجزء`` and may place it after a closing paragraph on the same page.
EXPLICIT_TOC = re.compile(r"(?:ال)?فهرس(?:\s*(?:الجزء|المحتويات))?")


def audit(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        books = int(conn.execute("SELECT COUNT(*) FROM books").fetchone()[0])
        pages = int(conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0])
        edition_rows = conn.execute(
            "SELECT book_id, canonical_book_id, edition_relation, "
            "searchable_by_default, page_count FROM books ORDER BY book_id"
        ).fetchall()
        default_search_books = sum(int(row[3]) for row in edition_rows)
        default_search_pages = sum(int(row[4]) for row in edition_rows if int(row[3]))
        edition_aliases = {
            row[0]: row[1] for row in edition_rows if row[0] != row[1]
        }
        suppressed_editions = [row[0] for row in edition_rows if not int(row[3])]
        exact_edition_page_matches = int(conn.execute(
            "SELECT COUNT(*) FROM pages excerpt JOIN pages canonical "
            "ON excerpt.norm_text=canonical.norm_text "
            "WHERE excerpt.book_id='b38' AND canonical.book_id='b37'"
        ).fetchone()[0])
        bayts = conn.execute(
            "SELECT qasida_number, bayt_number, stable_id FROM bayts "
            "WHERE book_id='b14' ORDER BY qasida_number, bayt_number"
        ).fetchall()

        malformed = []
        grouped: dict[int, list[int]] = {}
        seen_ids: set[str] = set()
        duplicate_ids: list[str] = []
        for row in bayts:
            q = int(row["qasida_number"])
            b = int(row["bayt_number"])
            stable_id = row["stable_id"]
            grouped.setdefault(q, []).append(b)
            if stable_id != f"b14-q{q:03d}-b{b:03d}":
                malformed.append(stable_id)
            if stable_id in seen_ids:
                duplicate_ids.append(stable_id)
            seen_ids.add(stable_id)

        continuous = sorted(grouped) == list(range(1, EXPECTED["qasidas"] + 1))
        continuous = continuous and all(
            values == list(range(1, max(values) + 1))
            for values in grouped.values()
        )

        heading_rows = conn.execute(
            "SELECT qasida_number, text FROM pages WHERE book_id='b14' "
            "AND text LIKE '%الْقَصِيدَة%' ORDER BY seq"
        ).fetchall()
        seen_qasidas: set[int] = set()
        ordinals: list[str] = []
        for row in heading_rows:
            q = int(row["qasida_number"])
            match = QASIDA_HEADING.search(row["text"])
            if match and q not in seen_qasidas:
                seen_qasidas.add(q)
                ordinals.append(match.group(1).strip())
        digest = hashlib.sha256("\n".join(ordinals).encode("utf-8")).hexdigest()

        suspicious_toc = []
        for row in conn.execute(
            "SELECT p.book_id, p.seq, p.text, b.page_count "
            "FROM pages p JOIN books b USING(book_id) WHERE p.block_type='toc'"
        ):
            at_boundary = row["seq"] <= 5 or row["seq"] / row["page_count"] >= 0.85
            if not at_boundary and not EXPLICIT_TOC.search(row["text"]):
                suspicious_toc.append(f"{row['book_id']}-p{row['seq']}")

        report = {
            "books": books,
            "pages": pages,
            "default_search_books": default_search_books,
            "default_search_pages": default_search_pages,
            "suppressed_editions": suppressed_editions,
            "canonical_aliases": edition_aliases,
            "b38_b37_exact_page_matches": exact_edition_page_matches,
            "qasidas": len(grouped),
            "bayts": len(bayts),
            "continuous_bayt_numbering": continuous,
            "malformed_stable_ids": malformed,
            "duplicate_stable_ids": duplicate_ids,
            "written_ordinals": len(ordinals),
            "ordinal_digest": digest,
            "suspicious_mid_book_toc": suspicious_toc,
        }
        failures = []
        for field in ("books", "pages", "qasidas", "bayts", "ordinal_digest"):
            if report[field] != EXPECTED[field]:
                failures.append(f"{field}: expected {EXPECTED[field]!r}, got {report[field]!r}")
        if not continuous:
            failures.append("bayt numbering is not continuous")
        if malformed:
            failures.append(f"malformed stable IDs: {malformed[:10]}")
        if duplicate_ids:
            failures.append(f"duplicate stable IDs: {duplicate_ids[:10]}")
        if len(ordinals) != EXPECTED["qasidas"]:
            failures.append(f"written ordinals: expected 95, got {len(ordinals)}")
        if suspicious_toc:
            failures.append(f"suspicious mid-book TOC pages: {suspicious_toc[:10]}")
        if default_search_books != EXPECTED["default_search_books"]:
            failures.append(
                f"default search books: expected 42, got {default_search_books}"
            )
        if default_search_pages != EXPECTED["default_search_pages"]:
            failures.append(
                f"default search pages: expected 6885, got {default_search_pages}"
            )
        if edition_aliases != {"b38": "b37"} or suppressed_editions != ["b38"]:
            failures.append(
                "edition policy mismatch: expected suppressed b38->b37 alias"
            )
        if exact_edition_page_matches < 30:
            failures.append(
                "b38 no longer has sufficient exact-page evidence for its b37 alias"
            )
        report["status"] = "pass" if not failures else "fail"
        report["failures"] = failures
        return report
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("db", nargs="?", type=Path, default=Path("library.db"))
    args = parser.parse_args()
    report = audit(args.db)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
