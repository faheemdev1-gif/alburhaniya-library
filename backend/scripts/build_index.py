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
import hashlib
import os
import sqlite3
import sys
import re

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app", "core"))
from book_parser import parse_book, parse_utf8_pages, split_oversized_pages   # noqa: E402
from arabic_utils import normalize_arabic, normalize_search_text  # noqa: E402
from text_format import clean_structured_bayt_text  # noqa: E402
from research_indexes import build_research_indexes   # noqa: E402

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

CREATE TABLE source_tiers (
    tier        INTEGER PRIMARY KEY CHECK (tier BETWEEN 1 AND 5),
    definition  TEXT NOT NULL
);

CREATE TABLE books (
    book_id        TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    page_count     INTEGER NOT NULL,
    source_grade   TEXT NOT NULL,   -- 'أصلي' | 'ثانوي'
    source_code    TEXT NOT NULL,   -- 'primary' | 'secondary'  (ASCII-safe)
    source_tier    INTEGER NOT NULL CHECK (source_tier BETWEEN 1 AND 5),
    source_author  TEXT,
    compiler       TEXT,
    authorship_mode TEXT NOT NULL,
    attribution_confidence TEXT NOT NULL
        CHECK (attribution_confidence IN ('high', 'medium', 'low', 'unverified')),
    provenance_status TEXT NOT NULL,
    source_note    TEXT,
    canonical_book_id TEXT NOT NULL,
    edition_relation TEXT NOT NULL DEFAULT 'canonical',
    searchable_by_default INTEGER NOT NULL DEFAULT 1
        CHECK (searchable_by_default IN (0, 1)),
    FOREIGN KEY (source_grade) REFERENCES grades(grade)
);
CREATE INDEX idx_books_default_search
    ON books(searchable_by_default, canonical_book_id);

CREATE TABLE pages (
    id            INTEGER PRIMARY KEY,
    book_id       TEXT NOT NULL,
    seq           INTEGER NOT NULL,
    printed_page  TEXT,
    citation_label TEXT,
    qasida_number INTEGER,
    qasida_title TEXT,
    qasida_bayt_count INTEGER,
    bayt_from INTEGER,
    bayt_to INTEGER,
    block_type TEXT NOT NULL DEFAULT 'body' CHECK (block_type IN ('body', 'toc')),
    text          TEXT NOT NULL,
    norm_text     TEXT NOT NULL,
    FOREIGN KEY (book_id) REFERENCES books(book_id)
);
CREATE INDEX idx_pages_book_seq ON pages(book_id, seq);
CREATE INDEX idx_pages_qasida ON pages(book_id, qasida_number, bayt_from);
CREATE INDEX idx_pages_block_type ON pages(block_type);

CREATE TABLE bayts (
    stable_id TEXT PRIMARY KEY,
    page_id INTEGER NOT NULL,
    book_id TEXT NOT NULL,
    qasida_number INTEGER NOT NULL,
    bayt_number INTEGER NOT NULL,
    start_char INTEGER NOT NULL,
    end_char INTEGER NOT NULL,
    text TEXT NOT NULL,
    norm_text TEXT NOT NULL,
    FOREIGN KEY (page_id) REFERENCES pages(id),
    UNIQUE (book_id, qasida_number, bayt_number)
);
CREATE INDEX idx_bayts_page ON bayts(page_id, start_char);
CREATE INDEX idx_bayts_structure ON bayts(book_id, qasida_number, bayt_number);

CREATE VIRTUAL TABLE pages_fts USING fts5(
    norm_text,
    content='pages',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);
"""


def slug_for(n: int) -> str:
    return f"b{n:02d}"


# A real Diwan heading is followed by its date.  Requiring that marker keeps
# prose such as "هذه القصيدة لها ثلاث قوافي: ..." from being mistaken for a
# new Qasida.  That note occurs after Qasida 4 in b14 and previously shifted
# every subsequent qasida_number by one (printed 62 was consequently indexed
# as 63).
_QASIDA_HEADING = re.compile(
    r"الْ?قَ?صِ?يدَ?ة\s+([^:\n]{1,80}):\s*([^\n]+?)"
    r"(?=\s+التّ?اريخ\s*:)"
)
_QASIDA_NUMERIC_DESIGNATOR = re.compile(
    r"^\s*(?:رقم\s*)?([0-9٠-٩۰-۹]{1,3})\s*$"
)
_DIGIT_TRANSLATION = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789",
)
_BAYT_NUMBER = re.compile(
    r"(?<![\d-])(\d{1,3})\s*-\s*(?=[\s(（\[\{«\"']{0,12}[\u0621-\u064A])"
)
_QASIDA_TITLE_END = re.compile(
    r"\s+التّ?اريخ\s*:|\s+\d{1,3}\s*-\s*(?=[ء-ي])"
)
_TOC_DOT_LEADER_SOURCE = r"(?:\.{3,}(?:\s+\.{1,3})*|…{2,})"
_TOC_DOT_LEADER = re.compile(_TOC_DOT_LEADER_SOURCE)
_TOC_TRAILING_PAGE_ENTRY = re.compile(
    _TOC_DOT_LEADER_SOURCE
    + r"\s*([0-9٠-٩۰-۹]{1,4})(?=\s|$)"
)
_TOC_EXPLICIT_HEADING = re.compile(
    r"(?:"
    r"الفهرس\s+الموضوع|"
    r"فهرس\s*(?:\([^)]{1,40}\)|-\s*)?\s*"
    r"(?:الجزء|المبحث|الموضوعات|المراجع|الصلوات|معاني|رقم\s+الجوهرة)|"
    r"انته[ىي]\s+فهرس"
    r")"
)
_TOC_MIN_ENTRY_DENSITY = 0.004
_PRINTED_PAGE_FOOTER = re.compile(
    r"(?:\[\s*([0-9٠-٩۰-۹]{1,4})\s*\]|-\s*([0-9٠-٩۰-۹]{1,4})\s*-)\s*$"
)
_FOOTNOTE_SEPARATOR = re.compile(r"(?:_{5,}|ـ{5,}|-{8,})")
_DIWAN_QASIDA_COUNT = 95
_DIWAN_BAYT_COUNT = 2682
_DIWAN_ORDINAL_DIGEST = "c354110999fb08d95a8d8d090fa63cc9eb47ddb62e4ea77e25b7261b66676a8d"


def classify_block(
    text: str, *, seq: int | None = None, page_count: int | None = None,
) -> str:
    """Identify contents pages without treating decorative dots as TOCs."""
    normalized = normalize_arabic(text, aggressive=True)
    if _TOC_EXPLICIT_HEADING.search(normalized):
        return "toc"

    entries = len(_TOC_TRAILING_PAGE_ENTRY.findall(text))
    if entries < 2 or entries / max(len(text), 1) < _TOC_MIN_ENTRY_DENSITY:
        return "body"

    if seq is not None and page_count is not None and page_count > 0:
        in_front_matter = seq <= 5
        in_back_matter = seq / page_count >= 0.85
        if not (in_front_matter or in_back_matter):
            return "body"
    return "toc"


def _source_footer_page(text: str) -> str | None:
    """Return the source-visible footer page, which is authoritative for b14."""
    match = _PRINTED_PAGE_FOOTER.search(text)
    if not match:
        return None
    return (match.group(1) or match.group(2)).translate(_DIGIT_TRANSLATION)


def _indexable_text(text: str) -> str:
    """Exclude only explicit end-footnote sections from FTS/census text."""
    marker = _FOOTNOTE_SEPARATOR.search(text or "")
    return text[:marker.start()].rstrip() if marker else (text or "")


def _qasida_bayt_count(text: str) -> int | None:
    """Extract the qaṣīda-wide count declared in its source heading."""
    normalized = normalize_arabic(
        text.translate(_DIGIT_TRANSLATION), aggressive=True,
    )
    match = re.search(r"عدد\s+الابيات\s*[:：]?\s*(\d{1,3})", normalized)
    return int(match.group(1)) if match else None


def annotate_diwan_pages(pages: list[dict]) -> list[dict]:
    """Carry qasida and bayt structure across b14 page boundaries."""
    qasida_number, qasida_title, qasida_bayt_count, last_bayt = 0, None, None, None
    page_count = len(pages)
    for seq, page in enumerate(pages, start=1):
        text = "\n\n".join(page["paragraphs"])
        source_page = _source_footer_page(text)
        if source_page is not None:
            # The visible source footer is the printed-page authority.  The
            # Shamela HTML marker is an export coordinate and is inconsistent
            # with the Dīwān's own page footer.
            page["printed_page"] = source_page
        heading = _QASIDA_HEADING.search(text)
        if heading:
            numeric = _QASIDA_NUMERIC_DESIGNATOR.fullmatch(heading.group(1))
            if numeric:
                # An explicit printed number is authoritative.  Do not feed
                # it through the sequential fallback: skipped single-digit
                # headings would otherwise shift every later qaṣīda.
                qasida_number = int(
                    numeric.group(1).translate(_DIGIT_TRANSLATION)
                )
            else:
                # Backward compatibility for older source files whose
                # headings use written Arabic ordinals.
                qasida_number += 1
            qasida_title = _QASIDA_TITLE_END.split(
                heading.group(2), maxsplit=1
            )[0].strip()
            qasida_bayt_count = _qasida_bayt_count(text)
            last_bayt = None
        bayts = [int(n) for n in _BAYT_NUMBER.findall(text)]
        page["qasida_number"] = qasida_number or None
        page["qasida_title"] = qasida_title
        page["qasida_bayt_count"] = qasida_bayt_count
        page["bayt_from"] = bayts[0] if bayts else last_bayt
        page["bayt_to"] = bayts[-1] if bayts else last_bayt
        page["block_type"] = classify_block(
            text, seq=seq, page_count=page_count,
        )
        if bayts:
            last_bayt = bayts[-1]
        if qasida_number and page["bayt_from"] is not None:
            span = (f"البيت {page['bayt_from']}" if page["bayt_from"] == page["bayt_to"]
                    else f"الأبيات {page['bayt_from']}–{page['bayt_to']}")
            locator = (
                f"الصفحة {page['printed_page']}، "
                if page.get("printed_page") else ""
            )
            total = (
                f" من {qasida_bayt_count}"
                if qasida_bayt_count is not None else ""
            )
            page["page_label"] = (
                f"القصيدة {qasida_number}، {locator}{span}{total}"
            )
    return pages


def validate_diwan_structure(conn: sqlite3.Connection) -> None:
    """Hard deployment gate for b14 structural and source-text integrity."""
    rows = conn.execute(
        "SELECT qasida_number, bayt_number FROM bayts "
        "WHERE book_id='b14' ORDER BY qasida_number, bayt_number"
    ).fetchall()
    qasidas: dict[int, list[int]] = {}
    for qasida_number, bayt_number in rows:
        qasidas.setdefault(int(qasida_number), []).append(int(bayt_number))
    expected_qasidas = list(range(1, _DIWAN_QASIDA_COUNT + 1))
    if sorted(qasidas) != expected_qasidas:
        raise RuntimeError(
            "D9 FAIL: expected qasidas 1..95, received "
            f"{sorted(qasidas)}"
        )
    if len(rows) != _DIWAN_BAYT_COUNT:
        raise RuntimeError(
            f"D9 FAIL: expected {_DIWAN_BAYT_COUNT} abyat, received {len(rows)}"
        )
    for number, bayt_numbers in qasidas.items():
        expected = list(range(1, max(bayt_numbers) + 1))
        if bayt_numbers != expected:
            missing = sorted(set(expected) - set(bayt_numbers))
            raise RuntimeError(
                f"D9 FAIL: qasida {number} has non-contiguous bayts; missing={missing}"
            )

    heading_rows = conn.execute(
        "SELECT qasida_number, text FROM pages WHERE book_id='b14' "
        "AND text LIKE '%الْقَصِيدَة%' ORDER BY seq"
    ).fetchall()
    designators: list[str] = []
    seen: set[int] = set()
    for qasida_number, text in heading_rows:
        heading = _QASIDA_HEADING.search(text)
        if not heading or qasida_number in seen:
            continue
        designator = heading.group(1).strip()
        if _QASIDA_NUMERIC_DESIGNATOR.fullmatch(designator):
            raise RuntimeError(
                f"D9 FAIL: qasida {qasida_number} display text rewrites its written ordinal"
            )
        seen.add(int(qasida_number))
        designators.append(designator)
    digest = hashlib.sha256("\n".join(designators).encode("utf-8")).hexdigest()
    if len(designators) != _DIWAN_QASIDA_COUNT or digest != _DIWAN_ORDINAL_DIGEST:
        raise RuntimeError(
            "D9 FAIL: written qasida ordinals do not match the canonical source"
        )


def build():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    mapping = json.load(open(MAPPING_FILE, encoding="utf-8"))
    sources = json.load(open(SOURCES_FILE, encoding="utf-8"))
    grades = sources["grades"]
    book_sources = sources["books"]
    book_tiers = sources["tiers"]["books"]
    tier_definitions = sources["tiers"]["definitions"]

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    for grade, g in grades.items():
        conn.execute(
            "INSERT INTO grades (grade, code, label, definition, usage) "
            "VALUES (?, ?, ?, ?, ?)",
            (grade, g["code"], g["label"], g["definition"], g["usage"]),
        )

    for tier, definition in tier_definitions.items():
        conn.execute(
            "INSERT INTO source_tiers (tier, definition) VALUES (?, ?)",
            (int(tier), definition),
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
        if slug == "b14":
            pages = annotate_diwan_pages(pages)

        src = book_sources.get(slug)
        if src is None:
            # Fail loud rather than silently shipping an ungraded book:
            # an ungraded book is worse than a missing one, because the
            # model will treat it as if it had no provenance caveat.
            missing.append(slug)
            continue

        tier = book_tiers.get(slug)
        if not isinstance(tier, int) or not 1 <= tier <= 5:
            missing.append(f"{slug} (missing numeric source tier 1-5)")
            continue

        grade = src["grade"]
        if grade not in grades:
            raise SystemExit(f"{slug}: unknown grade '{grade}' — not in sources.json grades")

        conn.execute(
            "INSERT INTO books "
            "(book_id, title, page_count, source_grade, source_code, source_tier, "
            "source_author, compiler, authorship_mode, attribution_confidence, "
            "provenance_status, source_note, canonical_book_id, edition_relation, "
            "searchable_by_default) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                slug,
                title,
                len(pages),
                grade,
                grades[grade]["code"],
                tier,
                src.get("author"),
                src.get("compiler"),
                src.get("authorship_mode", "unresolved"),
                src.get("attribution_confidence", "unverified"),
                src.get("provenance_status", "needs_review"),
                src.get("note"),
                src.get("canonical_book_id", slug),
                src.get("edition_relation", "canonical"),
                int(src.get("searchable_by_default", True)),
            ),
        )

        for seq, page in enumerate(pages, start=1):
            text = "\n\n".join(page["paragraphs"])
            norm = normalize_search_text(_indexable_text(text), level="safe")
            conn.execute(
                "INSERT INTO pages (book_id, seq, printed_page, citation_label, qasida_number, "
                "qasida_title, qasida_bayt_count, bayt_from, bayt_to, block_type, text, norm_text) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (slug, seq, page["printed_page"], page.get("page_label") or (
                    f"{title}، الصفحة {page['printed_page']}"
                    if page.get("printed_page")
                    else f"{title}، المقطع {seq}"
                 ),
                 page.get("qasida_number"), page.get("qasida_title"),
                 page.get("qasida_bayt_count"),
                 page.get("bayt_from"), page.get("bayt_to"),
                 page.get("block_type", classify_block(
                     text, seq=seq, page_count=len(pages),
                 )), text, norm),
            )
            page_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            if slug == "b14" and page.get("qasida_number"):
                markers = list(_BAYT_NUMBER.finditer(text))
                for i, marker in enumerate(markers):
                    number = int(marker.group(1))
                    start = marker.start()
                    end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
                    # Preserve raw page offsets, but do not copy the printed
                    # folio or decorative page rule into canonical verse text.
                    bayt_text = clean_structured_bayt_text(text[start:end].strip())
                    stable_id = f"{slug}-q{page['qasida_number']:03d}-b{number:03d}"
                    conn.execute(
                        "INSERT OR REPLACE INTO bayts (stable_id, page_id, book_id, qasida_number, "
                        "bayt_number, start_char, end_char, text, norm_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (stable_id, page_id, slug, page["qasida_number"], number,
                         start, end, bayt_text, normalize_arabic(bayt_text, aggressive=True)),
                    )
        total_pages += len(pages)
        print(f"{slug}  [{grades[grade]['code']:<9}] {len(pages):4d} pages  {title}")

    if missing:
        raise SystemExit(
            "\nERROR: these books have no entry in data/sources.json: "
            + ", ".join(missing)
            + "\nAdd them (with a grade) before building."
        )

    broken_editions = conn.execute(
        "SELECT b.book_id, b.canonical_book_id FROM books b "
        "LEFT JOIN books c ON c.book_id=b.canonical_book_id "
        "WHERE c.book_id IS NULL OR "
        "(b.searchable_by_default=0 AND b.canonical_book_id=b.book_id)"
    ).fetchall()
    if broken_editions:
        raise SystemExit(
            "ERROR: invalid canonical edition metadata: "
            + ", ".join(f"{row[0]}->{row[1]}" for row in broken_editions)
        )

    duplicates = conn.execute("SELECT book_id,printed_page FROM pages WHERE printed_page IS NOT NULL GROUP BY book_id,printed_page HAVING COUNT(*)>1").fetchall()
    for book_id, printed in duplicates:
        conn.execute("UPDATE pages SET citation_label=citation_label || ' [الموضع ' || book_id || '-p' || seq || '؛ ترقيم مطبوع مكرر]' WHERE book_id=? AND printed_page=?",(book_id,printed))
    from app.core.evidence_blocks import blocks
    conn.execute("CREATE TABLE evidence_blocks (page_id INTEGER, start_char INTEGER, end_char INTEGER, block_type TEXT, PRIMARY KEY(page_id,start_char))")
    for row in conn.execute("SELECT id,text,block_type FROM pages").fetchall():
        for block in blocks(row[1],row[2]):
            conn.execute("INSERT INTO evidence_blocks VALUES (?,?,?,?)",(row[0],block['start'],block['end'],block['type']))
    validate_diwan_structure(conn)
    research_stats = build_research_indexes(conn)
    from app.services.discovery_index import build_discovery_indexes
    print("Discovery index:", build_discovery_indexes(conn))

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
        f"({n_primary} primary / {n_secondary} secondary), {total_pages} pages, "
        f"{research_stats['tokens']} tokens, "
        f"{research_stats['parallel_candidates']} Dīwān parallel candidates"
    )


if __name__ == "__main__":
    build()
