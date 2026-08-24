#!/usr/bin/env python3
"""Add canonical-edition metadata to an existing library.db in place."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("LIBRARY_DB_PATH", ROOT / "library.db"))


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(books)").fetchall()
        }
        if "canonical_book_id" not in columns:
            conn.execute(
                "ALTER TABLE books ADD COLUMN canonical_book_id TEXT NOT NULL DEFAULT ''"
            )
        if "edition_relation" not in columns:
            conn.execute(
                "ALTER TABLE books ADD COLUMN edition_relation TEXT NOT NULL DEFAULT 'canonical'"
            )
        if "searchable_by_default" not in columns:
            conn.execute(
                "ALTER TABLE books ADD COLUMN searchable_by_default INTEGER NOT NULL DEFAULT 1"
            )
        conn.execute(
            "UPDATE books SET canonical_book_id=book_id "
            "WHERE canonical_book_id IS NULL OR canonical_book_id=''"
        )
        conn.execute(
            "UPDATE books SET canonical_book_id='b37', "
            "edition_relation='duplicate_excerpt', searchable_by_default=0 "
            "WHERE book_id='b38'"
        )
        conn.execute(
            "UPDATE books SET canonical_book_id='b37', "
            "edition_relation='canonical', searchable_by_default=1 "
            "WHERE book_id='b37'"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_books_default_search "
            "ON books(searchable_by_default, canonical_book_id)"
        )
        conn.commit()
        print(f"Migrated canonical-edition metadata in {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
