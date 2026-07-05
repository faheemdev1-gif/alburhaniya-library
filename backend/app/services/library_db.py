"""
Runtime access to library.db (built by scripts/build_index.py).

Pure exact-word search via SQLite FTS5 — no external search service,
no persistent disk required (the db ships baked into the Docker image).
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


def list_books() -> list[dict]:
    conn = _connection()
    rows = conn.execute("SELECT book_id, title, page_count FROM books ORDER BY title").fetchall()
    return [dict(r) for r in rows]


def get_book(book_id: str) -> dict | None:
    conn = _connection()
    row = conn.execute(
        "SELECT book_id, title, page_count FROM books WHERE book_id = ?", (book_id,)
    ).fetchone()
    return dict(row) if row else None


def get_page(book_id: str, seq: int) -> dict | None:
    conn = _connection()
    row = conn.execute(
        "SELECT book_id, seq, printed_page, text FROM pages WHERE book_id = ? AND seq = ?",
        (book_id, seq),
    ).fetchone()
    if not row:
        return None
    book = get_book(book_id)
    return {
        **dict(row),
        "book_title": book["title"] if book else None,
        "total_pages": book["page_count"] if book else None,
        "has_prev": seq > 1,
        "has_next": bool(book) and seq < book["page_count"],
    }


def search(query: str, book_ids: list[str] | None = None, limit: int = 2000) -> list[dict]:
    """
    Exact-word search across the whole library (or a subset of books),
    one result per matching page, sorted by book title then page order.
    """
    conn = _connection()
    norm_q = normalize_arabic(query, aggressive=True)
    if not norm_q:
        return []

    fts_query = '"' + norm_q.replace('"', '""') + '"'

    sql = """
        SELECT p.book_id, b.title AS book_title, p.seq, p.printed_page, p.text
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
    sql += " ORDER BY b.title, p.seq LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()

    pattern = _build_highlight_regex(query.strip())
    results = []
    for row in rows:
        safe_text = _esc(row["text"])
        highlighted, occ = _highlight(safe_text, pattern)
        if occ == 0:
            # FTS matched the normalized form (diacritics/alef variants
            # differed) but our tolerant regex still didn't line up —
            # fall back so we don't silently report 0 for a real match.
            occ = 1
            snippet = safe_text[:240] + ("…" if len(safe_text) > 240 else "")
        else:
            snippet = _make_snippet(safe_text, pattern)

        label = f"الصفحة {row['printed_page']}" if row["printed_page"] else f"المقطع {row['seq']}"
        results.append({
            "book_id": row["book_id"],
            "book_title": row["book_title"],
            "seq": row["seq"],
            "page_number": row["seq"],          # kept for frontend compatibility
            "page_label": label,
            "printed_page": row["printed_page"],
            "occurrences": occ,
            "highlight": highlighted,
            "snippet": snippet,
            "text": row["text"],
        })
    return results
