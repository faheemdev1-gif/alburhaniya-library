"""Live, read-only diagnostics for the indexed corpus contract."""
from __future__ import annotations

import hashlib
import re
import sqlite3
from typing import Any

DIWAN_QASIDA_COUNT = 95
DIWAN_BAYT_COUNT = 2682
DIWAN_ORDINAL_DIGEST = "c354110999fb08d95a8d8d090fa63cc9eb47ddb62e4ea77e25b7261b66676a8d"
_QASIDA_HEADING = re.compile(
    r"الْ?قَ?صِ?يدَ?ة\s+([^:\n]{1,80}):\s*([^\n]+?)"
    r"(?=\s+التّ?اريخ\s*:)"
)
_NUMERIC_DESIGNATOR = re.compile(r"^\s*(?:رقم\s*)?[0-9٠-٩۰-۹]{1,3}\s*$")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,),
    ).fetchone() is not None


def corpus_contract_snapshot(db_path: str | None = None) -> dict[str, Any]:
    """Compute the live D9 and research-index contract from the actual DB."""
    if db_path is None:
        from app.core.config import get_settings
        db_path = get_settings().library_db_path
    path = db_path
    conn = sqlite3.connect(path)
    try:
        book_count = int(conn.execute("SELECT COUNT(*) FROM books").fetchone()[0])
        page_count = int(conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0])
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
        edition_ok = (
            default_search_books == 42
            and default_search_pages == 6885
            and edition_aliases == {"b38": "b37"}
            and suppressed_editions == ["b38"]
        )
        rows = conn.execute(
            "SELECT qasida_number, bayt_number, stable_id FROM bayts "
            "WHERE book_id='b14' ORDER BY qasida_number, bayt_number"
        ).fetchall()
        grouped: dict[int, list[int]] = {}
        malformed_ids = 0
        for qasida, bayt, stable_id in rows:
            qasida = int(qasida)
            bayt = int(bayt)
            grouped.setdefault(qasida, []).append(bayt)
            expected_id = f"b14-q{qasida:03d}-b{bayt:03d}"
            malformed_ids += int(stable_id != expected_id)
        continuous = sorted(grouped) == list(range(1, DIWAN_QASIDA_COUNT + 1))
        if continuous:
            continuous = all(
                values == list(range(1, max(values) + 1))
                for values in grouped.values()
            )

        heading_rows = conn.execute(
            "SELECT qasida_number, text FROM pages WHERE book_id='b14' "
            "AND text LIKE '%الْقَصِيدَة%' ORDER BY seq"
        ).fetchall()
        designators: list[str] = []
        seen: set[int] = set()
        numeric_headings = 0
        for qasida, text in heading_rows:
            match = _QASIDA_HEADING.search(text)
            if not match or int(qasida) in seen:
                continue
            designator = match.group(1).strip()
            numeric_headings += int(bool(_NUMERIC_DESIGNATOR.fullmatch(designator)))
            seen.add(int(qasida))
            designators.append(designator)
        ordinal_digest = hashlib.sha256(
            "\n".join(designators).encode("utf-8")
        ).hexdigest()

        token_count = rooted_token_count = parallel_count = 0
        research_tables = _table_exists(conn, "tokens") and _table_exists(
            conn, "diwan_parallel_candidates"
        )
        if research_tables:
            token_count = int(conn.execute("SELECT COUNT(*) FROM tokens").fetchone()[0])
            rooted_token_count = int(conn.execute(
                "SELECT COUNT(*) FROM tokens WHERE root IS NOT NULL"
            ).fetchone()[0])
            parallel_count = int(conn.execute(
                "SELECT COUNT(*) FROM diwan_parallel_candidates"
            ).fetchone()[0])

        diwan_ok = (
            len(grouped) == DIWAN_QASIDA_COUNT
            and len(rows) == DIWAN_BAYT_COUNT
            and continuous
            and malformed_ids == 0
            and len(designators) == DIWAN_QASIDA_COUNT
            and numeric_headings == 0
            and ordinal_digest == DIWAN_ORDINAL_DIGEST
        )
        research_ok = research_tables and token_count > 0 and rooted_token_count > 0 and parallel_count > 0
        status = "ok" if book_count == 43 and edition_ok and diwan_ok and research_ok else "broken"
        return {
            "status": status,
            "books": book_count,
            "pages": page_count,
            "edition_deduplication": {
                "status": "ok" if edition_ok else "broken",
                "catalogue_books": book_count,
                "default_search_books": default_search_books,
                "default_search_pages": default_search_pages,
                "suppressed_editions": suppressed_editions,
                "canonical_aliases": edition_aliases,
                "policy": "canonical_by_default_explicit_edition_opt_in",
            },
            "diwan": {
                "status": "ok" if diwan_ok else "broken",
                "qasidas": len(grouped),
                "bayts": len(rows),
                "continuous_bayt_numbering": continuous,
                "malformed_stable_ids": malformed_ids,
                "written_ordinals": len(designators),
                "numeric_heading_rewrites": numeric_headings,
                "ordinal_digest": ordinal_digest,
            },
            "research_indexes": {
                "status": "ok" if research_ok else "broken",
                "tokens": token_count,
                "rooted_tokens": rooted_token_count,
                "parallel_candidates": parallel_count,
                "parallel_semantics": "unverified_candidates_only",
            },
        }
    finally:
        conn.close()
