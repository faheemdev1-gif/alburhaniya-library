#!/usr/bin/env python3
"""Backfill current citation metadata into an existing generated library.db.

Fresh deployments receive the same fields directly from build_index.py. This
migration exists for local verification and for operators who retain a built
database between releases.
"""
from __future__ import annotations

import os
import sqlite3

from build_index import (
    DB_PATH,
    _QASIDA_HEADING,
    _qasida_bayt_count,
    _source_footer_page,
    classify_block,
)


def migrate(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(pages)")
    }
    if "qasida_bayt_count" not in columns:
        conn.execute("ALTER TABLE pages ADD COLUMN qasida_bayt_count INTEGER")

    titles = {
        row["book_id"]: row["title"]
        for row in conn.execute("SELECT book_id, title FROM books")
    }
    current_qasida_count = None
    rows = conn.execute(
        "SELECT p.id, p.book_id, p.seq, p.printed_page, p.qasida_number, "
        "p.bayt_from, p.bayt_to, p.text, b.page_count "
        "FROM pages p JOIN books b USING(book_id) ORDER BY p.book_id, p.seq"
    ).fetchall()
    for row in rows:
        printed_page = row["printed_page"]
        qasida_count = None
        if row["book_id"] == "b14":
            source_page = _source_footer_page(row["text"])
            if source_page is not None:
                printed_page = source_page
            if _QASIDA_HEADING.search(row["text"]):
                current_qasida_count = _qasida_bayt_count(row["text"])
            qasida_count = current_qasida_count

        if row["qasida_number"] and row["bayt_from"] is not None:
            span = (
                f"البيت {row['bayt_from']}"
                if row["bayt_from"] == row["bayt_to"]
                else f"الأبيات {row['bayt_from']}–{row['bayt_to']}"
            )
            locator = f"الصفحة {printed_page}، " if printed_page else ""
            total = f" من {qasida_count}" if qasida_count is not None else ""
            citation_label = (
                f"القصيدة {row['qasida_number']}، {locator}{span}{total}"
            )
        else:
            locator = (
                f"الصفحة {printed_page}"
                if printed_page else f"المقطع {row['seq']}"
            )
            citation_label = f"{titles[row['book_id']]}، {locator}"

        conn.execute(
            "UPDATE pages SET printed_page=?, citation_label=?, "
            "qasida_bayt_count=?, block_type=? WHERE id=?",
            (
                printed_page,
                citation_label,
                qasida_count,
                classify_block(
                    row["text"], seq=row["seq"],
                    page_count=row["page_count"],
                ),
                row["id"],
            ),
        )
    conn.commit()
    conn.execute("PRAGMA optimize")
    conn.close()


if __name__ == "__main__":
    migrate(os.environ.get("LIBRARY_DB_PATH", DB_PATH))
