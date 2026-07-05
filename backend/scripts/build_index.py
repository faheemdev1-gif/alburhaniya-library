#!/usr/bin/env python3
"""
Build library.db (SQLite + FTS5) from data/raw_htm + data/mapping.json.

Runs once, at Docker build time, so the shipped image already contains a
ready-to-query search index. No persistent disk needed: every fresh
deploy rebuilds this file from the book sources baked into the image.
"""
from __future__ import annotations
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app", "core"))
from book_parser import parse_book                    # noqa: E402
from arabic_utils import normalize_arabic             # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")
RAW_DIR = os.path.join(DATA_DIR, "raw_htm")
MAPPING_FILE = os.path.join(DATA_DIR, "mapping.json")
DB_PATH = os.environ.get("LIBRARY_DB_PATH", os.path.join(HERE, "..", "library.db"))

SCHEMA = """
CREATE TABLE books (
    book_id     TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    page_count  INTEGER NOT NULL
);

CREATE TABLE pages (
    id            INTEGER PRIMARY KEY,
    book_id       TEXT NOT NULL,
    seq           INTEGER NOT NULL,
    printed_page  TEXT,
    text          TEXT NOT NULL,
    norm_text     TEXT NOT NULL,
    FOREIGN KEY (book_id) REFERENCES books(book_id)
);
CREATE INDEX idx_pages_book_seq ON pages(book_id, seq);

CREATE VIRTUAL TABLE pages_fts USING fts5(
    norm_text,
    content='pages',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);
"""


def slug_for(n: int) -> str:
    return f"b{n:02d}"


def build():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    mapping = json.load(open(MAPPING_FILE, encoding="utf-8"))
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    total_pages = 0
    for slug_in, title in sorted(mapping.items()):
        n = int(slug_in.split("_")[1])
        slug = slug_for(n)
        raw_path = os.path.join(RAW_DIR, f"{slug_in}.htm")
        pages = parse_book(raw_path)

        conn.execute(
            "INSERT INTO books (book_id, title, page_count) VALUES (?, ?, ?)",
            (slug, title, len(pages)),
        )
        for seq, page in enumerate(pages, start=1):
            text = "\n\n".join(page["paragraphs"])
            norm = normalize_arabic(text, aggressive=True)
            conn.execute(
                "INSERT INTO pages (book_id, seq, printed_page, text, norm_text) "
                "VALUES (?, ?, ?, ?, ?)",
                (slug, seq, page["printed_page"], text, norm),
            )
        total_pages += len(pages)
        print(f"{slug}  {len(pages):4d} pages  {title}")

    conn.execute("INSERT INTO pages_fts(rowid, norm_text) SELECT id, norm_text FROM pages")
    conn.commit()
    conn.execute("PRAGMA optimize")
    conn.close()
    print(f"\nBuilt {DB_PATH} — {len(mapping)} books, {total_pages} pages")


if __name__ == "__main__":
    build()
