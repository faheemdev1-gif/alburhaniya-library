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
from itertools import product

from app.core.config import get_settings
from app.core.arabic_utils import (
    ARABIC_STOPWORDS, hybrid_tokens, lexical_root, lexical_variants,
    normalize_arabic, normalized_tokens, term_variants,
)

_DIACRITIC_CLASS = (
    "[\u064b-\u065f\u0610-\u061a\u06d6-\u06dc\u06df-\u06e4\u06e7\u06e8\u06ea-\u06ed\u0640]*"
)
_ALEF = "\u0622\u0623\u0625\u0671\u0627"     # آأإٱا
_YA = "\u0649\u064a"                         # ىي
_TA = "\u0629\u0647"                         # ةه
_CHUNK_CHARS = 700
_CHUNK_OVERLAP = 120


def _concise_qasida_title(value: str | None) -> str | None:
    """Trim source records where a heading and the first bayts share one line."""
    if not value:
        return value
    title = re.split(
        r"\s+التّ?اريخ\s*:|\s+\d{1,3}\s*-\s*(?=[ء-ي])",
        value,
        maxsplit=1,
    )[0].strip()
    return title or value.strip()


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


def _build_exact_variant_regex(raw_query: str) -> re.Pattern:
    """Locate the same article-normalized forms accepted by exact FTS."""
    words = normalized_tokens(raw_query)
    if not words:
        return _build_highlight_regex(raw_query)
    patterns = []
    for parts in product(*(term_variants(word) for word in words)):
        patterns.append(_build_highlight_regex(" ".join(parts)).pattern)
    return re.compile("(?:" + "|".join(patterns) + ")", re.IGNORECASE)


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
        SELECT p.book_id, p.seq, p.printed_page, p.citation_label,
               p.qasida_number, p.qasida_title, p.bayt_from, p.bayt_to,
               p.block_type, p.text,
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
    d["qasida_title"] = _concise_qasida_title(d.get("qasida_title"))
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
    stems = set()
    for variant in lexical_variants(token):
        bare = _bare_lexeme(variant)
        stems.add(bare)
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
        # FTS token boundaries make معرفة and المعرفة distinct. Search both
        # definite and indefinite forms so exact mode does not silently lose
        # matches merely because the article is attached.
        choices = []
        for word in words:
            variants = {word}
            if word.startswith("ال") and len(word) > 4:
                variants.add(word[2:])
            elif len(word) >= 3:
                variants.add("ال" + word)
            choices.append(sorted(variants))
        phrases = [" ".join(parts) for parts in product(*choices)]
        return " OR ".join('"' + phrase.replace('"', '""') + '"' for phrase in phrases)
    if search_mode == "all_words":
        content_words = normalized_tokens(query, drop_stopwords=True) or words
        groups = []
        for word in content_words:
            variants = term_variants(word)
            groups.append("(" + " OR ".join(
                '"' + v.replace('"', '""') + '"' for v in variants
            ) + ")")
        return " AND ".join(groups)
    if search_mode == "any_word":
        return " OR ".join('"' + w.replace('"', '""') + '"' for w in words)
    raise ValueError("search_mode must be exact_phrase, all_words, any_word, or lexeme")


def _pattern_for_query(query: str, search_mode: str) -> re.Pattern:
    if search_mode == "exact_phrase":
        return _build_exact_variant_regex(query)
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
    *, book_ids=None, source_code=None, page_from=None, page_to=None,
    qasida_number=None
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
    if qasida_number is not None:
        sql += " AND p.qasida_number = ?"
        params.append(qasida_number)
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
        return {"matching_pages": 0, "normalized_occurrences": 0,
                "surface_occurrences": 0, "per_query": []}
    filters, params = _search_filters(
        book_ids=book_ids, source_code=source_code,
        page_from=page_from, page_to=page_to,
    )
    sql = """SELECT p.id, p.text FROM pages_fts
             JOIN pages p ON p.id = pages_fts.rowid
             JOIN books b ON b.book_id = p.book_id
             WHERE pages_fts MATCH ?""" + filters
    rows = _connection().execute(sql, [expression, *params]).fetchall()
    aggregate_patterns = [
        _pattern_for_query(
            q,
            "lexeme" if search_mode == "exact_phrase" and len(normalized_tokens(q)) == 1
            else search_mode,
        )
        for q in queries
    ]
    per_query = []
    for query in queries:
        q_expression = _fts_expression([query], "OR", search_mode)
        q_rows = _connection().execute(sql, [q_expression, *params]).fetchall()
        pattern = _pattern_for_query(
            query,
            "lexeme"
            if search_mode == "exact_phrase" and len(normalized_tokens(query)) == 1
            else search_mode,
        )
        surface_pattern = re.compile(re.escape(normalize_arabic(query, aggressive=False)))
        per_query.append({
            "query": query,
            "matching_pages": len(q_rows),
            "normalized_occurrences": sum(
                _unique_occurrence_count(r["text"], [pattern]) for r in q_rows
            ),
            "surface_occurrences": sum(
                len(surface_pattern.findall(normalize_arabic(r["text"], aggressive=False)))
                for r in q_rows
            ),
        })
        per_query[-1]["occurrences"] = per_query[-1]["normalized_occurrences"]
    normalized_occurrences = sum(
        _unique_occurrence_count(r["text"], aggregate_patterns) for r in rows
    )
    surface_occurrences = sum(
        sum(normalize_arabic(r["text"], aggressive=False).count(
            normalize_arabic(q, aggressive=False)) for q in queries)
        for r in rows
    )
    return {
        "matching_pages": len(rows),
        "normalized_occurrences": normalized_occurrences,
        "surface_occurrences": surface_occurrences,
        # Compatibility alias; unlike the old field its polarity is explicit.
        "matching_occurrences": normalized_occurrences,
        "per_query": per_query,
    }


def _ranking_order(ranking: str, diversified: bool = False) -> str:
    """Return deterministic SQL ordering with unambiguous column names."""
    book = "book_id" if diversified else "p.book_id"
    seq = "seq" if diversified else "p.seq"
    title = "book_title" if diversified else "b.title"
    source = "source_code" if diversified else "b.source_code"
    block = "block_type" if diversified else "p.block_type"
    structural = f"CASE WHEN {block} = 'toc' THEN 1 ELSE 0 END"
    if ranking == "relevance":
        prefix = "book_rank, " if diversified else ""
        return f"{structural}, {prefix}relevance, {title}, {book}, {seq}"
    if ranking == "primary_first":
        prefix = "book_rank, " if diversified else ""
        return f"{source}, {structural}, {prefix}relevance, {title}, {book}, {seq}"
    if ranking in {"book_order", "chronological"}:
        return f"{book}, {seq}"
    raise ValueError("ranking must be relevance, primary_first, chronological, or book_order")


def _bounded_bm25(raw_relevance: float) -> float:
    """Map positive FTS5 BM25 strength to a stable 0..1 lexical score.

    This fixed transform is query-independent and monotonic.  Unlike the old
    reciprocal-rank value, it does not change merely because ``limit`` or
    ``offset`` changes.
    """
    raw = max(0.0, float(raw_relevance))
    return raw / (raw + 5.0) if raw else 0.0


def _best_chunk_score(text: str, term_groups: list[tuple[str, ...]]) -> tuple[float, int]:
    """Return (0..1 quality, chunk start) for the best local window."""
    if not term_groups:
        return (0.0, 0)
    normalized = normalize_arabic(text, aggressive=True)
    best = 0.0
    step = _CHUNK_CHARS - _CHUNK_OVERLAP
    for start in range(0, max(1, len(normalized)), step):
        chunk = normalized[start:start + _CHUNK_CHARS]
        hits = [max((chunk.count(term) for term in group), default=0) for group in term_groups]
        coverage = sum(1 for n in hits if n) / len(term_groups)
        density = min(1.0, sum(hits) / len(term_groups))
        score = 0.8 * coverage + 0.2 * density
        if score > best:
            positions = [chunk.find(term) for group in term_groups for term in group
                         if chunk.find(term) >= 0]
            best, best_start = score, start + (min(positions) if positions else 0)
    return (best, locals().get("best_start", 0))


def _minimum_covering_span(
    text: str, term_groups: list[tuple[str, ...]]
) -> tuple[float, int, int]:
    """Return calibrated relevance and the smallest original-text term span."""
    if not term_groups:
        return (0.0, 0, 0)
    occurrences: list[tuple[int, int, int]] = []
    for group_index, variants in enumerate(term_groups):
        seen: set[tuple[int, int]] = set()
        for variant in variants:
            for match in _build_highlight_regex(variant).finditer(text):
                if match.span() not in seen:
                    occurrences.append((match.start(), match.end(), group_index))
                    seen.add(match.span())
    occurrences.sort()
    present = len({item[2] for item in occurrences})
    coverage = present / len(term_groups)
    if not occurrences:
        return (0.0, 0, 0)
    counts: dict[int, int] = {}
    left = 0
    best_span: tuple[int, int] | None = None
    for _, (_, end, group_index) in enumerate(occurrences):
        counts[group_index] = counts.get(group_index, 0) + 1
        while len(counts) == len(term_groups):
            start = occurrences[left][0]
            candidate = (start, end)
            if best_span is None or candidate[1] - candidate[0] < best_span[1] - best_span[0]:
                best_span = candidate
            left_group = occurrences[left][2]
            counts[left_group] -= 1
            if counts[left_group] == 0:
                del counts[left_group]
            left += 1
    if best_span is None:
        start, end, _ = occurrences[0]
        # Partial coverage remains useful for candidate generation but must not
        # cross the production relevance threshold on its own.
        return (round(0.70 * coverage, 6), start, end)
    start, end = best_span
    span_length = max(1, end - start)
    term_length = sum(min(len(v) for v in group) for group in term_groups)
    # Concept evidence often spans two or three adjacent sentences.  A
    # sentence-scale baseline avoids treating that as equivalent to terms
    # scattered across an entire page.
    proximity = 1.0 / (1.0 + span_length / max(180.0, term_length * 8.0))
    return (round(0.45 * coverage + 0.55 * proximity, 6), start, end)


def _evidence_excerpt(
    text: str, start: int, end: int, radius: int,
    patterns: list[re.Pattern] | None = None,
) -> str:
    """Return a bounded excerpt centred on the actual retrieval evidence."""
    radius = max(60, min(radius, 300))
    evidence_end = min(max(end, start + 1), start + radius)
    centre = (start + evidence_end) // 2
    left = max(0, centre - radius)
    right = min(len(text), centre + radius)
    excerpt = _esc(text[left:right])
    if patterns:
        union = re.compile("(?:" + "|".join(p.pattern for p in patterns) + ")", re.IGNORECASE)
        excerpt, _ = _highlight(excerpt, union)
    return ("…" if left else "") + excerpt + ("…" if right < len(text) else "")


_ARABIC_TOKEN_RE = re.compile(r"[\u0621-\u06ff]+")


def _content_query_terms(raw_queries: list[str]) -> list[tuple[str, str]]:
    """Return (display form, normalized form) for non-stopword query terms."""
    terms: list[tuple[str, str]] = []
    for query in raw_queries:
        for match in _ARABIC_TOKEN_RE.finditer(query):
            display = match.group(0)
            normalized = normalize_arabic(display, aggressive=True)
            if normalized and normalized not in ARABIC_STOPWORDS:
                terms.append((display, normalized))
    return terms


def _term_highlight_patterns(raw_queries: list[str]) -> list[re.Pattern]:
    """Build non-root, article-aware patterns for strict term evidence."""
    patterns: list[re.Pattern] = []
    seen: set[str] = set()
    for _, normalized in _content_query_terms(raw_queries):
        variants = sorted(set(term_variants(normalized)), key=len, reverse=True)
        pattern = re.compile(
            "(?:" + "|".join(_build_highlight_regex(v).pattern for v in variants) + ")",
            re.IGNORECASE,
        )
        if pattern.pattern not in seen:
            patterns.append(pattern)
            seen.add(pattern.pattern)
    return patterns


def _matched_terms(
    text: str, raw_queries: list[str], start: int | None = None,
    end: int | None = None,
) -> dict[str, dict[str, str]]:
    """Explain the corpus token that satisfied every strict terms token."""
    evidence_text = text[start:end] if start is not None and end is not None and end > start else text
    corpus_tokens = [match.group(0) for match in _ARABIC_TOKEN_RE.finditer(evidence_text)]
    normalized_corpus = [normalize_arabic(token, aggressive=True) for token in corpus_tokens]
    evidence: dict[str, dict[str, str]] = {}
    for display, normalized in _content_query_terms(raw_queries):
        allowed = set(term_variants(normalized))
        for corpus_form, corpus_normalized in zip(corpus_tokens, normalized_corpus):
            if corpus_normalized not in allowed:
                continue
            same_form = (
                normalize_arabic(corpus_form, aggressive=False)
                == normalize_arabic(display, aggressive=False)
            )
            evidence[display] = {
                "corpus_form": corpus_form,
                "relation": "exact" if same_form else "normalized",
            }
            break
    return evidence


def _matched_lexeme(text: str, raw_query: str) -> dict[str, dict[str, str]]:
    """Explain the surface form and relation used by a one-word lexeme hit."""
    query_terms = _content_query_terms([raw_query])
    if len(query_terms) != 1:
        return {}
    display, normalized = query_terms[0]
    match = _pattern_for_query(raw_query, "lexeme").search(text)
    if not match:
        return {}
    corpus_form = match.group(0)
    corpus_normalized = normalize_arabic(corpus_form, aggressive=True)
    if corpus_normalized == normalized:
        relation = "exact"
    elif corpus_normalized in set(term_variants(normalized)):
        relation = "normalized"
    else:
        relation = "root" if lexical_root(normalized) else "inflection"
    item = {"corpus_form": corpus_form, "relation": relation}
    root = lexical_root(normalized)
    if relation == "root" and root:
        item["root"] = root
    return {display: item}


def _bayt_at_offset(text: str, offset: int, qasida_number: int | None) -> tuple[int | None, str | None]:
    if qasida_number is None:
        return (None, None)
    markers = list(re.finditer(r"(?<![\d-])(\d{1,3})\s*-\s*(?=[\u0621-\u064A])", text))
    preceding = [m for m in markers if m.start() <= offset]
    if not preceding:
        return (None, None)
    number = int(preceding[-1].group(1))
    return (number, f"b14-q{qasida_number:03d}-b{number:03d}")


def _structural_identity(
    text: str, start: int, end: int, qasida_number: int | None,
) -> dict[str, object]:
    """Return a stable qasida container and bayt identity for an evidence span."""
    if qasida_number is None:
        return {}
    identity: dict[str, object] = {"container_id": f"b14-q{qasida_number:03d}"}
    start_number, start_id = _bayt_at_offset(text, start, qasida_number)
    end_number, end_id = _bayt_at_offset(text, max(start, end - 1), qasida_number)
    if start_number is None:
        return identity
    if end_number is None or end_number == start_number:
        identity.update({"bayt_number": start_number, "stable_id": start_id})
        return identity
    low, high = sorted((start_number, end_number))
    identity["stable_ids"] = [
        f"b14-q{qasida_number:03d}-b{number:03d}"
        for number in range(low, high + 1)
    ]
    return identity


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
    qasida_number: int | None = None,
    min_score: float = 0.0,
) -> list[dict]:
    """Arabic FTS search with explicit modes, ranking, and safe diversity."""
    raw_queries = queries or ([query] if query else [])
    expression = _fts_expression(raw_queries, operator, search_mode)
    if not expression:
        return []
    conn = _connection()
    filters, filter_params = _search_filters(
        book_ids=book_ids, source_code=source_code,
        page_from=page_from, page_to=page_to, qasida_number=qasida_number,
    )

    requested_limit, requested_offset = limit, offset
    requested_min = max(0.0, min(float(min_score or 0.0), 1.0))
    terms_pool = search_mode == "all_words"
    needs_post_filter = terms_pool or requested_min > 0.0
    if terms_pool:
        sql_limit = min(max((offset + limit) * 20, 100), 10_000)
    elif requested_min > 0.0:
        # A score threshold is applied to stable lexical evidence, not rank.
        # The complete 6,934-page corpus fits safely under this ceiling.
        sql_limit = 10_000
    else:
        sql_limit = limit
    sql_offset = 0 if needs_post_filter else offset

    # Diversification is useful across a library, but it must never truncate a
    # deliberately selected single book.
    apply_diversity = bool(
        diversify_books and not terms_pool and (not book_ids or len(book_ids) > 1)
    )

    base = """
        SELECT p.book_id, b.title AS book_title, b.source_grade, b.source_code,
               b.source_tier, p.seq, p.printed_page, p.citation_label,
               p.qasida_number, p.qasida_title, p.bayt_from, p.bayt_to,
               p.block_type, p.text,
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
        params.extend((max(1, max_per_book), sql_limit, sql_offset))
    else:
        order = _ranking_order(ranking, diversified=False)
        sql = base + " ORDER BY " + order + " LIMIT ? OFFSET ?"
        params.extend((sql_limit, sql_offset))
    rows = conn.execute(sql, params).fetchall()

    patterns = [_pattern_for_query(q.strip(), search_mode) for q in raw_queries if q and q.strip()]
    term_patterns = _term_highlight_patterns(raw_queries) if search_mode == "all_words" else []
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
            "qasida_number": row["qasida_number"],
            "qasida_title": _concise_qasida_title(row["qasida_title"]),
            "bayt_from": row["bayt_from"], "bayt_to": row["bayt_to"],
            "block_type": row["block_type"],
            "snippet": snippet,
            "_raw_relevance": -float(row["relevance"]),
            "match_type": {
                "exact_phrase": "exact", "all_words": "terms",
                "any_word": "terms", "lexeme": "lexeme",
            }[search_mode],
        }
        first_match = min((m.start() for m, _ in matches), default=0)
        if search_mode == "all_words":
            groups = [term_variants(w) for q in raw_queries
                      for w in normalized_tokens(q, drop_stopwords=True)]
            local_score, span_start, span_end = _minimum_covering_span(plain_text, groups)
            first_match = span_start
            evidence_end = span_end
            result["_local_score"] = local_score
            result["occurrences"] = _unique_occurrence_count(plain_text, term_patterns)
            result["matched_terms"] = _matched_terms(
                plain_text, raw_queries, span_start, span_end,
            )
            if span_end > span_start:
                result["snippet"] = _evidence_excerpt(
                    plain_text, span_start, span_end, context_chars, term_patterns,
                )
        elif search_mode == "lexeme" and raw_queries:
            result["matched_terms"] = _matched_lexeme(plain_text, raw_queries[0])
            evidence_end = min((m.end() for m, _ in matches), default=first_match + 1)
        else:
            evidence_end = min((m.end() for m, _ in matches), default=first_match + 1)
        if row["book_id"] == "b14":
            result.update(_structural_identity(
                plain_text, first_match, evidence_end, row["qasida_number"],
            ))
        result["match_id"] = f"{row['book_id']}-p{row['seq']}-c{first_match}"
        result["evidence_span"] = {
            "start": first_match,
            "end": evidence_end,
            "excerpt": result["snippet"],
        }
        if include_full_text:
            safe_text = _esc(plain_text)
            for pattern in patterns:
                safe_text, _ = _highlight(safe_text, pattern)
            result["highlight"] = safe_text
            result["text"] = plain_text
        results.append(result)
    for item in results:
        raw_bm25 = item.pop("_raw_relevance", 0.0)
        bm25_score = _bounded_bm25(raw_bm25)
        structural = 0.15 if item.get("block_type") == "toc" else 1.0
        if search_mode == "all_words":
            local_score = item.pop("_local_score", 0.0)
            occurrence_score = item.get("occurrences", 0) / (item.get("occurrences", 0) + 2.0)
            score = structural * (
                0.55 * local_score + 0.35 * bm25_score + 0.10 * occurrence_score
            )
            item["score_kind"] = "term_proximity_bm25"
        else:
            score = structural * bm25_score
            item["score_kind"] = {
                "exact_phrase": "bm25_phrase",
                "any_word": "bm25_any_term",
                "lexeme": "bm25_lexeme",
            }[search_mode]
        item["score"] = round(max(0.0, min(1.0, score)), 6)
    if search_mode == "all_words":
        if ranking in {"book_order", "chronological"}:
            results.sort(key=lambda item: (item["book_id"], item["seq"]))
        elif ranking == "primary_first":
            results.sort(key=lambda item: (
                item["source_code"] != "primary", item.get("block_type") == "toc",
                -item["score"], item["source_tier"], item["book_id"], item["seq"],
            ))
        else:
            results.sort(key=lambda item: (
                item.get("block_type") == "toc", -item["score"],
                item["source_tier"], item["book_id"], item["seq"],
            ))
    if requested_min > 0.0:
        results = [item for item in results if item["score"] >= requested_min]
    if terms_pool:
        if diversify_books and not (book_ids and len(book_ids) == 1):
            counts: dict[str, int] = {}
            diversified = []
            for item in results:
                if counts.get(item["book_id"], 0) < max(1, max_per_book):
                    diversified.append(item)
                    counts[item["book_id"]] = counts.get(item["book_id"], 0) + 1
            results = diversified
        results = results[requested_offset: requested_offset + requested_limit]
    elif requested_min > 0.0:
        results = results[requested_offset: requested_offset + requested_limit]
    for rank, item in enumerate(results, start=requested_offset + 1):
        item["rank"] = rank
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
    filtered_queries = []
    for query in queries:
        words = hybrid_tokens(query)
        if words:
            filtered_queries.append(" ".join(words))
    queries = filtered_queries or queries
    limit = int(kwargs.get("limit", 10))
    offset = int(kwargs.get("offset", 0))
    pool = min(max((offset + limit) * 8, 40), 400)
    rrf_scores: dict[tuple[str, int], float] = {}
    mode_scores: dict[tuple[str, int], dict[str, float]] = {}
    records: dict[tuple[str, int], dict] = {}
    # Candidate generation stays page-level (the shipped index has pages), but
    # final co-occurrence is measured in overlapping local chunks.
    term_groups = [lexical_variants(w) for q in queries for w in q.split()]
    concept_queries = sorted({variant for group in term_groups for variant in group})
    for mode, weight in (("exact_phrase", 1.0), ("all_words", 0.8), ("any_word", 0.2)):
        call = dict(kwargs)
        call.update(search_mode=mode, limit=pool, offset=0, diversify_books=False)
        call.pop("query", None)
        call.pop("min_score", None)
        call["queries"] = concept_queries if mode == "any_word" else queries
        if mode == "any_word":
            call["operator"] = "OR"
        for rank, row in enumerate(search(**call), start=1):
            key = (row["book_id"], row["seq"])
            rrf_scores[key] = rrf_scores.get(key, 0.0) + weight / (60 + rank)
            mode_scores.setdefault(key, {})[mode] = max(
                mode_scores.get(key, {}).get(mode, 0.0), float(row["score"]),
            )
            records.setdefault(key, row)
    chunk_starts = {}
    chunk_ends = {}
    local_scores = {}
    for key, row in records.items():
        page = get_page(row["book_id"], row["seq"])
        best, chunk_start, chunk_end = (
            _minimum_covering_span(page["text"], term_groups)
            if page else (0.0, 0, 0)
        )
        chunk_starts[key] = chunk_start
        chunk_ends[key] = chunk_end
        local_scores[key] = best
    max_rrf = sum(weight / 61.0 for weight in (1.0, 0.8, 0.2))
    calibrated_scores: dict[tuple[str, int], float] = {}
    for key, row in records.items():
        supports = mode_scores.get(key, {})
        lexical_support = (
            0.50 * supports.get("exact_phrase", 0.0)
            + 0.30 * supports.get("all_words", 0.0)
            + 0.20 * supports.get("any_word", 0.0)
        )
        fusion_support = min(1.0, rrf_scores.get(key, 0.0) / max_rrf) if max_rrf else 0.0
        score = 0.62 * local_scores.get(key, 0.0) + 0.28 * lexical_support + 0.10 * fusion_support
        page = get_page(row["book_id"], row["seq"])
        if page and page.get("block_type") == "toc":
            score *= 0.15
        calibrated_scores[key] = round(max(0.0, min(1.0, score)), 6)
    ordered = sorted(
        records,
        key=lambda key: (-calibrated_scores[key], records[key]["source_tier"],
                         records[key]["book_id"], records[key]["seq"]),
    )
    ranking = kwargs.get("ranking", "relevance")
    if ranking in {"book_order", "chronological"}:
        ordered.sort(key=lambda key: (records[key]["book_id"], records[key]["seq"]))
    elif ranking == "primary_first":
        ordered.sort(key=lambda key: (
            records[key]["source_code"] != "primary", -calibrated_scores[key],
            records[key]["source_tier"], records[key]["book_id"], records[key]["seq"],
        ))
    fused = []
    configured_threshold = getattr(get_settings(), "hybrid_min_relevance", 0.55)
    eligible = [key for key in ordered if local_scores.get(key, 0.0) >= configured_threshold]
    requested_min = max(0.0, min(float(kwargs.get("min_score") or 0.0), 1.0))
    calibrated = [
        (key, calibrated_scores[key]) for key in eligible
        if calibrated_scores[key] >= requested_min
    ]
    hybrid_patterns = [
        re.compile(
            "(?:" + "|".join(_build_highlight_regex(v).pattern for v in group) + ")",
            re.IGNORECASE,
        )
        for group in term_groups
    ]
    for key, calibrated_score in calibrated[offset: offset + limit]:
        row = records[key]
        row["score"] = calibrated_score
        row["score_kind"] = "hybrid_evidence"
        row["match_id"] = f"{row['book_id']}-p{row['seq']}-c{chunk_starts[key]}"
        row["match_type"] = "hybrid"
        page = get_page(row["book_id"], row["seq"])
        if page:
            row["snippet"] = _evidence_excerpt(
                page["text"], chunk_starts[key], chunk_ends[key],
                int(kwargs.get("context_chars", 160)), hybrid_patterns,
            )
            row["evidence_span"] = {
                "start": chunk_starts[key],
                "end": chunk_ends[key],
                "excerpt": row["snippet"],
            }
            if row["book_id"] == "b14":
                row.update(_structural_identity(
                    page["text"], chunk_starts[key], chunk_ends[key],
                    row.get("qasida_number"),
                ))
        fused.append(row)
    for rank, row in enumerate(fused, start=offset + 1):
        row["rank"] = rank
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
    return {key: value for key, value in {
        "book_id": page["book_id"], "book_title": page["book_title"],
        "tier": page["source_tier"], "seq": page["seq"],
        "printed_page": page["printed_page"], "citation_label": page["citation_label"],
        "qasida_number": page.get("qasida_number"), "qasida_title": page.get("qasida_title"),
        "bayt_from": page.get("bayt_from"), "bayt_to": page.get("bayt_to"),
        "occurrences": occurrences,
        "passage": passage, "page_chars": len(text),
        "truncated": len(passage) < len(text),
    }.items() if value is not None}


def get_passage_by_match_id(match_id: str, context_chars: int = 800) -> dict | None:
    match = _MATCH_ID_RE.fullmatch(match_id or "")
    if not match:
        return None
    book_id, seq, start = match.group(1), int(match.group(2)), int(match.group(3))
    return get_passage(book_id, seq, context_chars=context_chars, match_start=start)


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
