"""
Runtime access to library.db (built by scripts/build_index.py).

Pure exact-word search via SQLite FTS5 — no external search service,
no persistent disk required (the db ships baked into the Docker image).

Source grading: every book carries source_grade ('أصلي' | 'ثانوي') and
source_code ('primary' | 'secondary'). The grade rides along with EVERY
search hit and page read, so a model never has to make an extra call to
find out whether what it's quoting is the shaykh's own words or a
disciple's commentary. The verbose Arabic definition of each grade lives
in the `grades` table and is fetched once per session (see get_grades),
not stapled onto every row.

Token budget rule of thumb:
  - grade + code (short)      -> included in list_books, search, get_page
  - author + note (longer)    -> included in get_book / read_book only
"""
from __future__ import annotations
import re
import sqlite3
from functools import lru_cache
from html import escape as _esc

from app.core.config import get_settings
from app.core.arabic_utils import normalize_arabic

_DIACRITIC_CLASS = (
    "[\u064b-\u065f\u0610-\u061a\u06d6-\u06dc\u06df-\u06e4\u06e7\u06e8\u06ea-\u06ed\u0640]*"
)
_ALEF = "\u0622\u0623\u0625\u0671\u0627"     # آأإٱا
_YA = "\u0649\u064a"                         # ىي
_TA = "\u0629\u0647"                         # ةه


@lru_cache(maxsize=1)
def _connection() -> sqlite3.Connection:
    s = get_settings()
    conn = sqlite3.connect(s.library_db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _tolerant_char_pattern(ch: str) -> str:
    if ch in _ALEF:
        return f"[{_ALEF}]"
    if ch in _YA:
        return f"[{_YA}]"
    if ch in _TA:
        return f"[{_TA}]"
    return re.escape(ch)


def _build_highlight_regex(raw_query: str) -> re.Pattern:
    """A regex that finds `raw_query` in un-normalized text, tolerating
    diacritics and alef/ya/ta-marbuta variants — so highlighting lines up
    with what FTS5 (searching normalized text) actually matched."""
    parts = [_tolerant_char_pattern(c) for c in raw_query.strip()]
    pattern = _DIACRITIC_CLASS.join(parts)
    return re.compile(pattern, re.IGNORECASE)


def _highlight(text: str, pattern: re.Pattern) -> tuple[str, int]:
    count = 0

    def _sub(m):
        nonlocal count
        count += 1
        return f"<mark>{m.group(0)}</mark>"

    return pattern.sub(_sub, text), count


def _make_snippet(plain_text: str, pattern: re.Pattern, radius: int = 120) -> str:
    """
    Trim a long page down to a window around the first match, THEN
    highlight — never slice already-tagged HTML, which could cut a
    <mark>/</mark> tag in half.
    """
    m = pattern.search(plain_text)
    if not m:
        window = plain_text[: radius * 2]
        prefix, suffix = "", "…" if len(plain_text) > radius * 2 else ""
    else:
        start = max(0, m.start() - radius)
        end = min(len(plain_text), m.end() + radius)
        window = plain_text[start:end]
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(plain_text) else ""
    highlighted_window, _ = _highlight(window, pattern)
    return prefix + highlighted_window + suffix


# ---------------------------------------------------------------- grades

@lru_cache(maxsize=1)
def get_grades() -> dict:
    """The source-grade legend: definition + how to weigh each grade.

    Cached — this is static reference data. Send it to a model ONCE per
    session (e.g. in list_books), not on every row.
    """
    conn = _connection()
    rows = conn.execute(
        "SELECT grade, code, label, definition, usage FROM grades"
    ).fetchall()
    return {r["grade"]: dict(r) for r in rows}


# ----------------------------------------------------------------- books

def list_books() -> list[dict]:
    """Every book with its source grade (short form — no note/author)."""
    conn = _connection()
    rows = conn.execute(
        "SELECT book_id, title, page_count, source_grade, source_code "
        "FROM books ORDER BY source_code, title"
    ).fetchall()
    return [dict(r) for r in rows]


def get_book(book_id: str) -> dict | None:
    """Full metadata for one book, including the provenance note."""
    conn = _connection()
    row = conn.execute(
        "SELECT book_id, title, page_count, source_grade, source_code, "
        "       source_author, source_note "
        "FROM books WHERE book_id = ?",
        (book_id,),
    ).fetchone()
    return dict(row) if row else None


@lru_cache(maxsize=64)
def _book_grade(book_id: str) -> tuple[str | None, str | None, int]:
    """(grade, code, page_count) — cheap, cached, used on hot paths."""
    conn = _connection()
    row = conn.execute(
        "SELECT source_grade, source_code, page_count, title FROM books WHERE book_id = ?",
        (book_id,),
    ).fetchone()
    if not row:
        return (None, None, 0)
    return (row["source_grade"], row["source_code"], row["page_count"])


# ----------------------------------------------------------------- pages

def get_page(book_id: str, seq: int) -> dict | None:
    conn = _connection()
    row = conn.execute(
        """
        SELECT p.book_id, p.seq, p.printed_page, p.text,
               b.title AS book_title, b.page_count AS total_pages,
               b.source_grade, b.source_code
        FROM pages p
        JOIN books b ON b.book_id = p.book_id
        WHERE p.book_id = ? AND p.seq = ?
        """,
        (book_id, seq),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["has_prev"] = seq > 1
    d["has_next"] = seq < d["total_pages"]
    return d


# ---------------------------------------------------------------- search

def search(
    query: str,
    book_ids: list[str] | None = None,
    source_code: str | None = None,
    page_from: int | None = None,
    page_to: int | None = None,
    limit: int = 10,
    offset: int = 0,
    context_chars: int = 160,
    include_full_text: bool = False,
) -> list[dict]:
    """
    Exact-word search across the whole library (or a subset of books),
    one result per matching page, sorted by grade (primary first), then
    book title, then page order.

    Results intentionally contain a short excerpt instead of the complete
    page. Fetch a selected page with get_page(); returning the page here as
    both plain and highlighted text used to dominate MCP token consumption.
    """
    conn = _connection()
    norm_q = normalize_arabic(query, aggressive=True)
    if not norm_q:
        return []

    fts_query = '"' + norm_q.replace('"', '""') + '"'

    sql = """
        SELECT p.book_id, b.title AS book_title, b.source_grade, b.source_code,
               p.seq, p.printed_page, p.text
        FROM pages_fts
        JOIN pages p ON p.id = pages_fts.rowid
        JOIN books b ON b.book_id = p.book_id
        WHERE pages_fts MATCH ?
    """
    params: list = [fts_query]
    if book_ids:
        placeholders = ",".join("?" for _ in book_ids)
        sql += f" AND p.book_id IN ({placeholders})"
        params.extend(book_ids)
    if source_code:
        sql += " AND b.source_code = ?"
        params.append(source_code)
    if page_from is not None:
        sql += " AND p.seq >= ?"
        params.append(page_from)
    if page_to is not None:
        sql += " AND p.seq <= ?"
        params.append(page_to)
    # source_code sorts 'primary' < 'secondary' alphabetically — so the
    # shaykh's own words come first without any extra CASE expression.
    sql += " ORDER BY b.source_code, b.title, p.seq LIMIT ? OFFSET ?"
    params.extend((limit, offset))

    rows = conn.execute(sql, params).fetchall()

    pattern = _build_highlight_regex(query.strip())
    results = []
    for row in rows:
        plain_text = row["text"]
        _, occ = _highlight(plain_text, pattern)
        if occ == 0:
            # FTS matched the normalized form (diacritics/alef variants
            # differed) but our tolerant regex still didn't line up —
            # fall back so we don't silently report 0 for a real match.
            occ = 1
            snippet = _esc(plain_text[: context_chars * 2])
            if len(plain_text) > context_chars * 2:
                snippet += "…"
        else:
            snippet = _make_snippet(_esc(plain_text), pattern, radius=context_chars)

        label = f"الصفحة {row['printed_page']}" if row["printed_page"] else f"المقطع {row['seq']}"
        result = {
            "book_id": row["book_id"],
            "book_title": row["book_title"],
            "source_grade": row["source_grade"],   # أصلي | ثانوي
            "source_code": row["source_code"],     # primary | secondary
            "seq": row["seq"],
            "page_number": row["seq"],             # frontend compatibility
            "page_label": label,
            "printed_page": row["printed_page"],
            "occurrences": occ,
            "snippet": snippet,
        }
        if include_full_text:
            # Legacy REST clients may still depend on these fields. MCP search
            # deliberately leaves them out and uses get_page for full content.
            safe_text = _esc(plain_text)
            result["highlight"], _ = _highlight(safe_text, pattern)
            result["text"] = plain_text
        results.append(result)
    return results
