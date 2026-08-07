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
from difflib import get_close_matches
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
    """Find a normalized query in original Arabic while retaining display text."""
    # Strip query tashkil first. Otherwise a fully-vowelled query places literal
    # diacritics into the regex and its offsets no longer align reliably.
    normalized_query = normalize_arabic(raw_query, aggressive=False)
    parts = [_tolerant_char_pattern(c) for c in normalized_query.strip()]
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


@lru_cache(maxsize=1)
def get_tiers() -> dict:
    """The numeric 1-5 evidential hierarchy, lower number = higher weight."""
    rows = _connection().execute(
        "SELECT tier, definition FROM source_tiers ORDER BY tier"
    ).fetchall()
    return {str(r["tier"]): r["definition"] for r in rows}


# ----------------------------------------------------------------- books

def list_books() -> list[dict]:
    """Every book with its source grade (short form — no note/author)."""
    conn = _connection()
    rows = conn.execute(
        "SELECT book_id, title, page_count, source_grade, source_code, source_tier "
        "FROM books ORDER BY source_tier, title"
    ).fetchall()
    return [dict(r) for r in rows]


def get_book(book_id: str) -> dict | None:
    """Full metadata for one book, including the provenance note."""
    conn = _connection()
    row = conn.execute(
        "SELECT book_id, title, page_count, source_grade, source_code, source_tier, "
        "       source_author, source_note "
        "FROM books WHERE book_id = ?",
        (book_id,),
    ).fetchone()
    return dict(row) if row else None


def resolve_book_scope(scope: str) -> list[str]:
    """Resolve an Arabic title/series fragment to book ids.

    Matching uses the same Arabic normalization as page search, so callers do
    not need to list the catalogue merely to discover ids.  A scope such as
    ``شرح شراب الوصل`` deliberately resolves every volume in that series.
    """
    needle = normalize_arabic(scope or "", aggressive=True).strip()
    if not needle:
        return []
    rows = _connection().execute(
        "SELECT book_id, title, source_tier FROM books ORDER BY source_tier, book_id"
    ).fetchall()
    exact, partial = [], []
    for row in rows:
        title = normalize_arabic(row["title"], aggressive=True)
        if title == needle:
            exact.append(row["book_id"])
        elif needle in title:
            partial.append(row["book_id"])
    # An exact title names one work; a partial title commonly names a series.
    return exact or partial


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
        SELECT p.book_id, p.seq, p.printed_page, p.citation_label, p.text,
               b.title AS book_title, b.page_count AS total_pages,
               b.source_grade, b.source_code, b.source_tier
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

_PROCLITICS = ("وال", "فال", "بال", "كال", "لل", "ال", "و", "ف", "ب", "ل", "ك")
_LEXEME_PREFIXES = ("", "ال", "و", "ف", "ب", "ل", "ك", "وال", "فال", "بال", "كال", "لل")
_LEXEME_SUFFIXES = ("", "ه", "ها", "هم", "هن", "ك", "كم", "كما", "كن", "نا", "يه", "يات")


def _bare_lexeme(token: str) -> str:
    for prefix in _PROCLITICS:
        if token.startswith(prefix) and len(token) - len(prefix) >= 3:
            return token[len(prefix):]
    return token


def _lexeme_stems(token: str) -> list[str]:
    """Conservative light expansion for one Arabic lexeme.

    FTS prefix matching covers attached suffixes.  The ي/ا alternation covers
    weak-final forms such as حمى/حماك/حماية without pretending to be a full
    Arabic root analyser.
    """
    bare = _bare_lexeme(token)
    stems = {bare}
    if bare.endswith("ي"):
        stems.add(bare[:-1] + "ا")
    elif bare.endswith("ا"):
        stems.add(bare[:-1] + "ي")
    return sorted(stems)


def _query_expression(query: str, search_mode: str = "exact_phrase") -> str:
    normalized = normalize_arabic(query, aggressive=True)
    if not normalized:
        return ""
    words = [w for w in normalized.split() if w]
    if search_mode == "lexeme":
        if len(words) != 1:
            raise ValueError("lexeme search supports one Arabic word per query")
        stems = _lexeme_stems(words[0])
        variants = sorted({
            prefix + stem + suffix
            for stem in stems
            for prefix in _LEXEME_PREFIXES
            for suffix in _LEXEME_SUFFIXES
        })
        return " OR ".join('"' + v.replace('"', '""') + '"' for v in variants)
    if search_mode == "exact_phrase":
        return '"' + normalized.replace('"', '""') + '"'
    if search_mode == "all_words":
        return " AND ".join('"' + w.replace('"', '""') + '"' for w in words)
    if search_mode == "any_word":
        return " OR ".join('"' + w.replace('"', '""') + '"' for w in words)
    raise ValueError("search_mode must be exact_phrase, all_words, any_word, or lexeme")


def _pattern_for_query(query: str, search_mode: str) -> re.Pattern:
    if search_mode != "lexeme":
        return _build_highlight_regex(query)
    normalized = normalize_arabic(query, aggressive=True)
    words = normalized.split()
    if len(words) != 1:
        raise ValueError("lexeme search supports one Arabic word per query")
    stems = _lexeme_stems(words[0])
    stem_patterns = []
    for stem in stems:
        chars = [_tolerant_char_pattern(c) for c in stem]
        stem_patterns.append(_DIACRITIC_CLASS.join(chars))
    def word_pattern(word: str) -> str:
        return _DIACRITIC_CLASS.join(_tolerant_char_pattern(c) for c in word)
    prefix_patterns = [word_pattern(p) for p in _LEXEME_PREFIXES if p]
    suffix_patterns = [word_pattern(s) for s in _LEXEME_SUFFIXES if s]
    prefix = "(?:" + "|".join(prefix_patterns) + ")?"
    suffix = "(?:" + "|".join(suffix_patterns) + ")?"
    start_boundary = r"(?<![\u0621-\u064A])"
    boundary = r"(?![\u0621-\u064A])"
    return re.compile(
        start_boundary + prefix + "(?:" + "|".join(stem_patterns) + ")" + suffix + boundary,
        re.IGNORECASE,
    )


def _unique_occurrence_count(text: str, patterns: list[re.Pattern]) -> int:
    return len({m.span() for pattern in patterns for m in pattern.finditer(text)})


def _fts_expression(
    queries: list[str], operator: str = "OR", search_mode: str = "exact_phrase"
) -> str:
    expressions = [_query_expression(q, search_mode) for q in queries]
    expressions = [e for e in expressions if e]
    if not expressions:
        return ""
    joiner = " OR " if operator.upper() == "OR" else " AND "
    return joiner.join(f"({e})" for e in expressions)

def _search_filters(
    *, book_ids=None, source_code=None, page_from=None, page_to=None
) -> tuple[str, list]:
    sql, params = "", []
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
    return sql, params


def count_search(
    queries: list[str], operator: str = "OR", book_ids: list[str] | None = None,
    source_code: str | None = None, page_from: int | None = None,
    page_to: int | None = None, search_mode: str = "exact_phrase",
) -> int:
    """Return the true number of matching page/segments."""
    expression = _fts_expression(queries, operator, search_mode)
    if not expression:
        return 0
    filters, params = _search_filters(
        book_ids=book_ids, source_code=source_code,
        page_from=page_from, page_to=page_to,
    )
    row = _connection().execute(
        """SELECT COUNT(*) AS n FROM pages_fts
           JOIN pages p ON p.id = pages_fts.rowid
           JOIN books b ON b.book_id = p.book_id
           WHERE pages_fts MATCH ?""" + filters,
        [expression, *params],
    ).fetchone()
    return int(row["n"])


def search_stats(
    queries: list[str], operator: str = "OR", book_ids: list[str] | None = None,
    source_code: str | None = None, page_from: int | None = None,
    page_to: int | None = None, search_mode: str = "exact_phrase",
) -> dict:
    """Return explicit page and occurrence census, including each alternative."""
    expression = _fts_expression(queries, operator, search_mode)
    if not expression:
        return {"matching_pages": 0, "matching_occurrences": 0, "per_query": []}
    filters, params = _search_filters(
        book_ids=book_ids, source_code=source_code,
        page_from=page_from, page_to=page_to,
    )
    sql = """SELECT p.id, p.text FROM pages_fts
             JOIN pages p ON p.id = pages_fts.rowid
             JOIN books b ON b.book_id = p.book_id
             WHERE pages_fts MATCH ?""" + filters
    rows = _connection().execute(sql, [expression, *params]).fetchall()
    aggregate_patterns = [_pattern_for_query(q, search_mode) for q in queries]
    per_query = []
    for query in queries:
        q_expression = _fts_expression([query], "OR", search_mode)
        q_rows = _connection().execute(sql, [q_expression, *params]).fetchall()
        pattern = _pattern_for_query(query, search_mode)
        per_query.append({
            "query": query,
            "matching_pages": len(q_rows),
            "occurrences": sum(_unique_occurrence_count(r["text"], [pattern]) for r in q_rows),
        })
    return {
        "matching_pages": len(rows),
        "matching_occurrences": sum(
            _unique_occurrence_count(r["text"], aggregate_patterns) for r in rows
        ),
        "per_query": per_query,
    }


def _ranking_order(ranking: str, diversified: bool = False) -> str:
    prefix = "source_code, " if ranking == "primary_first" else ""
    if ranking == "relevance":
        return prefix + ("book_rank, relevance, book_title, seq" if diversified else "relevance, book_title, seq")
    if ranking == "primary_first":
        return "source_code, " + ("book_rank, relevance, book_title, seq" if diversified else "relevance, book_title, seq")
    if ranking in {"book_order", "chronological"}:
        return prefix + "book_id, seq"
    raise ValueError("ranking must be relevance, primary_first, chronological, or book_order")


def search(
    query: str | None = None,
    queries: list[str] | None = None,
    operator: str = "OR",
    search_mode: str = "exact_phrase",
    ranking: str = "primary_first",
    book_ids: list[str] | None = None,
    source_code: str | None = None,
    page_from: int | None = None,
    page_to: int | None = None,
    limit: int = 10,
    offset: int = 0,
    context_chars: int = 160,
    include_full_text: bool = False,
    diversify_books: bool = True,
    max_per_book: int = 2,
) -> list[dict]:
    """Arabic FTS search with explicit modes, ranking, and safe diversity."""
    raw_queries = queries or ([query] if query else [])
    expression = _fts_expression(raw_queries, operator, search_mode)
    if not expression:
        return []
    conn = _connection()
    filters, filter_params = _search_filters(
        book_ids=book_ids, source_code=source_code,
        page_from=page_from, page_to=page_to,
    )

    # Diversification is useful across a library, but it must never truncate a
    # deliberately selected single book.
    apply_diversity = bool(diversify_books and (not book_ids or len(book_ids) > 1))

    base = """
        SELECT p.book_id, b.title AS book_title, b.source_grade, b.source_code,
               b.source_tier, p.seq, p.printed_page, p.citation_label, p.text,
               bm25(pages_fts) AS relevance
        FROM pages_fts
        JOIN pages p ON p.id = pages_fts.rowid
        JOIN books b ON b.book_id = p.book_id
        WHERE pages_fts MATCH ?
    """ + filters
    params = [expression, *filter_params]
    if apply_diversity:
        order = _ranking_order(ranking, diversified=True)
        sql = """WITH matched AS (""" + base + """), ranked AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY book_id ORDER BY relevance, seq
            ) AS book_rank
            FROM matched
        )
        SELECT * FROM ranked WHERE book_rank <= ?
        ORDER BY """ + order + " LIMIT ? OFFSET ?"
        params.extend((max(1, max_per_book), limit, offset))
    else:
        order = _ranking_order(ranking, diversified=False)
        sql = base + " ORDER BY " + order + " LIMIT ? OFFSET ?"
        params.extend((limit, offset))
    rows = conn.execute(sql, params).fetchall()

    patterns = [_pattern_for_query(q.strip(), search_mode) for q in raw_queries if q and q.strip()]
    results = []
    for row in rows:
        plain_text = row["text"]
        matches = [(pat.search(plain_text), pat) for pat in patterns]
        matches = [(m, pat) for m, pat in matches if m]
        if matches:
            _, pattern = min(matches, key=lambda x: x[0].start())
            occ = _unique_occurrence_count(plain_text, patterns)
            snippet = _make_snippet(plain_text, pattern, radius=context_chars)
        else:
            occ = 1
            snippet = _esc(plain_text[: context_chars * 2])
            if len(plain_text) > context_chars * 2:
                snippet += "…"

        label = f"الصفحة {row['printed_page']}" if row["printed_page"] else f"المقطع {row['seq']}"
        result = {
            "book_id": row["book_id"], "book_title": row["book_title"],
            "source_grade": row["source_grade"], "source_code": row["source_code"],
            "source_tier": row["source_tier"],
            "seq": row["seq"], "page_number": row["seq"], "page_label": label,
            "printed_page": row["printed_page"], "occurrences": occ,
            "citation_label": row["citation_label"],
            "snippet": snippet,
            "score": round(1.0 / (1.0 + abs(float(row["relevance"]))), 6),
        }
        first_match = min((m.start() for m, _ in matches), default=0)
        result["match_id"] = f"{row['book_id']}-p{row['seq']}-c{first_match}"
        if include_full_text:
            safe_text = _esc(plain_text)
            for pattern in patterns:
                safe_text, _ = _highlight(safe_text, pattern)
            result["highlight"] = safe_text
            result["text"] = plain_text
        results.append(result)
    return results


def hybrid_search(**kwargs) -> list[dict]:
    """Local hybrid lexical retrieval using reciprocal-rank fusion.

    The exact phrase, all-terms and any-term signals complement one another:
    exact wording receives the strongest vote while concept-like queries still
    recover pages whose words are separated.  This remains fully local and
    deterministic; an external embedding service is therefore not required at
    request time.
    """
    queries = kwargs.get("queries") or ([kwargs.get("query")] if kwargs.get("query") else [])
    limit = int(kwargs.get("limit", 10))
    offset = int(kwargs.get("offset", 0))
    pool = min(max((offset + limit) * 8, 40), 400)
    scores: dict[tuple[str, int], float] = {}
    records: dict[tuple[str, int], dict] = {}
    for mode, weight in (("exact_phrase", 1.0), ("all_words", 0.8), ("any_word", 0.35)):
        call = dict(kwargs)
        call.update(search_mode=mode, limit=pool, offset=0, diversify_books=False)
        call.pop("query", None)
        call["queries"] = queries
        for rank, row in enumerate(search(**call), start=1):
            key = (row["book_id"], row["seq"])
            scores[key] = scores.get(key, 0.0) + weight / (60 + rank)
            records.setdefault(key, row)
    ordered = sorted(
        records,
        key=lambda key: (
            records[key]["source_tier"], -scores[key], records[key]["book_id"], records[key]["seq"]
        ),
    )
    fused = []
    for key in ordered[offset: offset + limit]:
        row = records[key]
        row["score"] = round(scores[key], 6)
        fused.append(row)
    return fused


def _paragraph_window(text: str, match_start: int, match_end: int, context_chars: int) -> tuple[int, int]:
    """Prefer complete paragraph boundaries while enforcing a bounded window."""
    hard_start = max(0, match_start - context_chars)
    hard_end = min(len(text), match_end + context_chars)
    para_start = text.rfind("\n\n", hard_start, match_start)
    para_end = text.find("\n\n", match_end, hard_end)
    start = para_start + 2 if para_start >= 0 else hard_start
    end = para_end if para_end >= 0 else hard_end
    return start, end


_MATCH_ID_RE = re.compile(r"^(b\d+)-p(\d+)-c(\d+)$")


def get_passage(
    book_id: str, seq: int, query: str | None = None, context_chars: int = 800,
    match_start: int | None = None,
) -> dict | None:
    """Return coherent bounded context around a normalized Arabic match."""
    page = get_page(book_id, seq)
    if page is None:
        return None
    pattern = _build_highlight_regex(query.strip()) if query else None
    text = page["text"]
    match = pattern.search(text) if pattern else None
    if match is None and match_start is not None:
        match_start = max(0, min(match_start, len(text)))
        match_end = min(len(text), match_start + 1)
        start, end = _paragraph_window(text, match_start, match_end, context_chars)
        passage = ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")
        occurrences = None
    elif match:
        start, end = _paragraph_window(text, match.start(), match.end(), context_chars)
        passage = text[start:end]
        prefix, suffix = ("…" if start else ""), ("…" if end < len(text) else "")
        passage, occurrences = _highlight(passage, pattern)
        passage = prefix + passage + suffix
    else:
        passage = text[: context_chars * 2]
        occurrences = 0
    return {
        "book_id": page["book_id"], "book_title": page["book_title"],
        "source": page["source_code"], "seq": page["seq"],
        "printed_page": page["printed_page"], "citation_label": page["citation_label"],
        "occurrences": occurrences,
        "passage": passage, "page_chars": len(text),
        "truncated": len(passage) < len(text),
    }


def get_passage_by_match_id(match_id: str, context_chars: int = 800) -> dict | None:
    match = _MATCH_ID_RE.fullmatch(match_id or "")
    if not match:
        return None
    book_id, seq, start = match.group(1), int(match.group(2)), int(match.group(3))
    result = get_passage(book_id, seq, context_chars=context_chars, match_start=start)
    if result is not None:
        result["match_id"] = match_id
    return result


@lru_cache(maxsize=1)
def _indexed_terms() -> tuple[str, ...]:
    """Small vocabulary used only for no-result spelling suggestions."""
    rows = _connection().execute("SELECT norm_text FROM pages").fetchall()
    terms: set[str] = set()
    for row in rows:
        terms.update(w for w in row["norm_text"].split() if 2 <= len(w) <= 30)
    return tuple(sorted(terms))


def suggest_spelling(query: str, limit: int = 5) -> list[str]:
    normalized = normalize_arabic(query, aggressive=True)
    if not normalized or " " in normalized:
        return []
    return get_close_matches(normalized, _indexed_terms(), n=max(1, limit), cutoff=0.82)
