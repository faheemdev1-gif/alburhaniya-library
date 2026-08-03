#!/usr/bin/env python3
"""
Build library.db (SQLite + FTS5) from data/raw_htm (or data/raw_utf8) +
data/mapping.json + data/sources.json.

Runs once, at Docker build time, so the shipped image already contains a
ready-to-query search index. No persistent disk needed: every fresh
deploy rebuilds this file from the book sources baked into the image.

Source grading (added):
  data/sources.json carries, for every book_id, its source grade
  (أصلي / ثانوي) plus author + a short book-specific note. The long
  boilerplate definition of each grade is stored ONCE in the `grades`
  table — not repeated per book, and NEVER written into `pages`, which
  would pollute the FTS index with 43 identical copies of high-value
  words like العقيدة / المشايخ / سيدي الإمام فخر الدين.

Two source formats (added):
  Most books are shamela.ws .htm exports (windows-1256), parsed by
  parse_book(). Some books use modern Unicode that windows-1256 can't
  represent at all (e.g. the ﷺ ligature, Quranic ornate brackets ﴿ ﴾,
  Arabic-Indic digits) — those live as pre-segmented UTF-8 JSON in
  data/raw_utf8/ instead, parsed by parse_utf8_pages(). Both return the
  same {"printed_page", "paragraphs"} shape, so everything downstream
  (DB insert, FTS indexing) is identical either way.
"""
from __future__ import annotations
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app", "core"))
from book_parser import parse_book, parse_utf8_pages, split_oversized_pages   # noqa: E402
from arabic_utils import normalize_arabic             # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")
RAW_DIR = os.path.join(DATA_DIR, "raw_htm")
RAW_UTF8_DIR = os.path.join(DATA_DIR, "raw_utf8")
MAPPING_FILE = os.path.join(DATA_DIR, "mapping.json")
SOURCES_FILE = os.path.join(DATA_DIR, "sources.json")
DB_PATH = os.environ.get("LIBRARY_DB_PATH", os.path.join(HERE, "..", "library.db"))

SCHEMA = """
CREATE TABLE grades (
    grade       TEXT PRIMARY KEY,   -- 'أصلي' | 'ثانوي'
    code        TEXT NOT NULL,      -- 'primary' | 'secondary'
    label       TEXT NOT NULL,
    definition  TEXT NOT NULL,      -- the Arabic boilerplate, stored ONCE
    usage       TEXT NOT NULL       -- how a model should weigh it
);

CREATE TABLE books (
    book_id        TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    page_count     INTEGER NOT NULL,
    source_grade   TEXT NOT NULL,   -- 'أصلي' | 'ثانوي'
    source_code    TEXT NOT NULL,   -- 'primary' | 'secondary'  (ASCII-safe)
    source_author  TEXT,
    source_note    TEXT,
    FOREIGN KEY (source_grade) REFERENCES grades(grade)
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
    sources = json.load(open(SOURCES_FILE, encoding="utf-8"))
    grades = sources["grades"]
    book_sources = sources["books"]

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    for grade, g in grades.items():
        conn.execute(
            "INSERT INTO grades (grade, code, label, definition, usage) "
            "VALUES (?, ?, ?, ?, ?)",
            (grade, g["code"], g["label"], g["definition"], g["usage"]),
        )

    missing: list[str] = []
    total_pages = 0

    for slug_in, title in sorted(mapping.items()):
        n = int(slug_in.split("_")[1])
        slug = slug_for(n)

        htm_path = os.path.join(RAW_DIR, f"{slug_in}.htm")
        utf8_path = os.path.join(RAW_UTF8_DIR, f"{slug_in}.json")
        if os.path.exists(htm_path):
            pages = parse_book(htm_path)
        elif os.path.exists(utf8_path):
            pages = parse_utf8_pages(utf8_path)
        else:
            # Neither source file exists for this mapping entry — treat
            # like any other missing book rather than crashing here, so
            # the loud error at the end lists everything wrong in one go.
            missing.append(f"{slug} (no {slug_in}.htm or {slug_in}.json found)")
            continue

        # Protect the API from pathological source records (notably b02,
        # whose source export has no real page markers). Ordinary pages are
        # unchanged; only oversized records are segmented.
        pages = split_oversized_pages(pages)

        src = book_sources.get(slug)
        if src is None:
            # Fail loud rather than silently shipping an ungraded book:
            # an ungraded book is worse than a missing one, because the
            # model will treat it as if it had no provenance caveat.
            missing.append(slug)
            continue

        grade = src["grade"]
        if grade not in grades:
            raise SystemExit(f"{slug}: unknown grade '{grade}' — not in sources.json grades")

        conn.execute(
            "INSERT INTO books "
            "(book_id, title, page_count, source_grade, source_code, source_author, source_note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                slug,
                title,
                len(pages),
                grade,
                grades[grade]["code"],
                src.get("author"),
                src.get("note"),
            ),
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
        print(f"{slug}  [{grades[grade]['code']:<9}] {len(pages):4d} pages  {title}")

    if missing:
        raise SystemExit(
            "\nERROR: these books have no entry in data/sources.json: "
            + ", ".join(missing)
            + "\nAdd them (with a grade) before building."
        )

    # NOTE: only `pages` feeds the FTS index. Grades / notes / authors
    # deliberately stay out of it.
    conn.execute("INSERT INTO pages_fts(rowid, norm_text) SELECT id, norm_text FROM pages")
    conn.commit()
    conn.execute("PRAGMA optimize")
    conn.close()

    n_primary = sum(1 for s in book_sources.values() if s["grade"] == "أصلي")
    n_secondary = len(book_sources) - n_primary
    print(
        f"\nBuilt {DB_PATH} — {len(mapping)} books "
        f"({n_primary} primary / {n_secondary} secondary), {total_pages} pages"
    )


if __name__ == "__main__":
    build()