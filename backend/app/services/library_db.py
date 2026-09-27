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
import os
import re
import sqlite3
import threading
from time import perf_counter
from app.core.observability import profiled, record_phase, record_candidates
from difflib import get_close_matches
from functools import lru_cache
from html import escape as _esc
from itertools import product
from collections.abc import Iterable

from app.core.config import get_settings
from app.core.arabic_utils import (
    ARABIC_STOPWORDS, hybrid_tokens, lexical_root, lexical_variants,
    normalize_arabic, normalize_search_text, normalize_ya, normalized_tokens,
    remove_tatweel, safe_term_variants, safe_tokens, strip_diacritics,
    term_variants,
)
from app.core.text_format import clean_structured_bayt_text

_DIACRITIC_CLASS = (
    "[\u064b-\u065f\u0610-\u061a\u06d6-\u06dc\u06df-\u06e4\u06e7\u06e8\u06ea-\u06ed\u0640]*"
)
_ALEF = "\u0622\u0623\u0625\u0671\u0627"     # آأإٱا
_YA = "\u0649\u064a"                         # ىي
_TA = "\u0629\u0647"                         # ةه
_CHUNK_CHARS = 700
_CHUNK_OVERLAP = 120
_BAYT_MARKER_RE = re.compile(
    r"(?<![\d-])(\d{1,3})\s*-\s*(?=[\s(（\[\{«\"']{0,12}[\u0621-\u064A])"
)
_QASIDA_HEADING_RE = re.compile(
    r"الْ?قَ?صِ?يدَ?ة\s+[^:\n]{1,80}:\s*[^\n]+?(?=\s+التّ?اريخ\s*:)"
)
_COMPARISON_PREFIXES = ("وال", "فال", "بال", "كال", "لل", "ال")
_ARABIC_BOUNDARY = r"[\u0621-\u06ff]"
_FOOTNOTE_SEPARATOR_RE = re.compile(r"(?:_{5,}|ـ{5,}|-{8,})")
_QURAN_RANGE_RE = re.compile(
    r"]\s*([^\]\[]*[\u0621-\u06ff][^\]\[]]{6,800}?)\s*\["
    r"|﴿([^﴿﴾]{3,800})﴾"
)
_HADITH_RANGE_RE = re.compile(r"[?؟\"“]([^?؟\"”]{8,600})[?؟\"”]")

# Authority affects ordering, never the evidence score itself.  The maximum
# adjustment is 0.10, so a substantial relevance gap always wins.  Keeping a
# separate rank_score prevents source policy from corrupting score semantics.
_PRIMARY_SOURCE_BOOST = 0.05
_TIER_BOOST_STEP = 0.01


def authority_adjusted_score(
    score: float, source_code: str, source_tier: int,
) -> float:
    """Return the documented primary-first ordering score."""
    tier = max(1, min(int(source_tier), 5))
    source_boost = _PRIMARY_SOURCE_BOOST if source_code == "primary" else 0.0
    tier_boost = (6 - tier) * _TIER_BOOST_STEP
    return round(float(score) + source_boost + tier_boost, 6)


def _set_rank_score(item: dict) -> float:
    value = authority_adjusted_score(
        item["score"], item["source_code"], item["source_tier"],
    )
    item["rank_score"] = value
    return value


def primary_first_sort_key(item: dict) -> tuple:
    """Deterministic authority-adjusted ordering used across all modes."""
    return (
        item.get("block_type") == "toc",
        -_set_rank_score(item),
        -float(item["score"]),
        item["source_tier"],
        item["book_id"],
        item["seq"],
    )


def ranking_policy(ranking: str) -> str:
    """Short public explanation of the active result-ordering policy."""
    if ranking == "primary_first":
        return "authority_adjusted_relevance_v1"
    if ranking == "relevance":
        return "evidence_score_descending"
    return "stable_book_sequence"


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


def _connection() -> sqlite3.Connection:
    """One read-only connection per worker thread.

    The former process-wide connection used ``check_same_thread=False`` and
    could be entered concurrently by FastAPI/FastMCP workers.  Thread-local
    readers avoid shared cursor/transaction state while retaining connection
    reuse and SQLite page caching.
    """
    from app.core.budget import expired,check
    check()
    s = get_settings()
    path = os.path.abspath(s.library_db_path)
    state = getattr(_connection, "_state", None)
    if state is None:
        state = threading.local()
        _connection._state = state
    conn = getattr(state, "conn", None)
    if conn is not None and getattr(state, "path", None) == path:
        return conn
    if conn is not None:
        conn.close()
    conn = sqlite3.connect(path, timeout=2.0)
    conn.row_factory = sqlite3.Row
    conn.set_progress_handler(lambda: int(expired()),10000)
    conn.execute("PRAGMA query_only = ON")
    conn.execute("PRAGMA busy_timeout = 1500")
    state.conn = conn
    state.path = path
    return conn


def _tolerant_char_pattern(ch: str, *, normalization_level: str = "safe") -> str:
    if normalization_level in {"safe", "broad"} and ch == "ك":
        return "[كکڪ]"
    if normalization_level == "broad" and ch in _ALEF:
        return f"[{_ALEF}]"
    if normalization_level == "broad" and ch in _YA:
        return f"[{_YA}]"
    if normalization_level == "broad" and ch in _TA:
        return f"[{_TA}]"
    return re.escape(ch)


@lru_cache(maxsize=2048)
def _build_highlight_regex(
    raw_query: str, *, whole_word: bool = True,
    normalization_level: str = "safe",
) -> re.Pattern:
    """Find a normalized query in original Arabic while retaining display text."""
    # Strip query tashkil first. Otherwise a fully-vowelled query places literal
    # diacritics into the regex and its offsets no longer align reliably.
    normalized_query = normalize_search_text(raw_query, level=normalization_level)
    words = normalized_query.split()
    if not words:
        return re.compile(r"(?!x)x")
    word_patterns = []
    for word in words:
        parts = [
            _tolerant_char_pattern(c, normalization_level=normalization_level)
            for c in word
        ]
        word_patterns.append(_DIACRITIC_CLASS.join(parts) + _DIACRITIC_CLASS)
    pattern = r"(?:[\s\u060c\u061b\u061f،؛؟.,:;!()\[\]{}]+)".join(word_patterns)
    if whole_word:
        pattern = rf"(?<!{_ARABIC_BOUNDARY}){pattern}(?!{_ARABIC_BOUNDARY})"
    return re.compile(pattern, re.IGNORECASE)


def conjunction_variants(variants):
    """Safe spacing variants, not a change to literal census normalization."""
    output=set(variants)
    for word in variants:
        if word.startswith('و') and len(word)>3:
            for tail in safe_term_variants(word[1:]):output.update(('و'+tail,'و '+tail))
    return sorted(output)


@lru_cache(maxsize=2048)
def _build_exact_variant_regex(
    raw_query: str, *, whole_word: bool = True,
    normalization_level: str = "safe",
) -> re.Pattern:
    """Locate the same article-normalized forms accepted by exact FTS."""
    words = safe_tokens(re.sub(r'\bو\s+(?=[ء-ي])','و',raw_query))
    if not words:
        return _build_highlight_regex(
            raw_query, whole_word=whole_word,
            normalization_level=normalization_level,
        )
    # Factor alternatives per word instead of compiling the Cartesian product
    # of complete phrases (2**N for an N-word question).
    groups = []
    for word in words:
        groups.append("(?:" + "|".join(
            _build_highlight_regex(variant, whole_word=False,
                normalization_level=normalization_level).pattern
            for variant in conjunction_variants(safe_term_variants(word))
        ) + ")")
    separator = r"(?:[\s\u060c\u061b\u061f،؛؟.,:;!()\[\]{}]+)"
    phrase = separator.join(groups)
    if whole_word:
        phrase = rf"(?<!{_ARABIC_BOUNDARY}){phrase}(?!{_ARABIC_BOUNDARY})"
    return re.compile(phrase, re.IGNORECASE)


def _indexable_text(text: str) -> str:
    """Return authorial/page text eligible for search and census.

    Only an explicit footnote rule is removed. Ambiguous inline parenthetical
    material remains indexed; conservative exclusion is safer than silently
    deleting source prose.
    """
    marker = _FOOTNOTE_SEPARATOR_RE.search(text or "")
    value = text[:marker.start()].rstrip() if marker else (text or "")
    from app.core.evidence_blocks import INCLUDE_TOC, body_text
    return value if INCLUDE_TOC.get() else body_text(value)


@lru_cache(maxsize=8192)
def _content_ranges(pattern: re.Pattern, text: str) -> tuple[tuple[int, int], ...]:
    return tuple((match.start(), match.end()) for match in pattern.finditer(text or ""))


def content_types(text: str) -> list[str]:
    """Conservative content labels present on a page."""
    values = {"body"}
    if _QASIDA_HEADING_RE.search(text or ""):
        values.add("heading")
    if _QURAN_RANGE_RE.search(text or ""):
        values.add("quran")
    if _HADITH_RANGE_RE.search(text or ""):
        values.add("hadith")
    if _FOOTNOTE_SEPARATOR_RE.search(text or ""):
        values.add("footnote")
    return sorted(values)


def evidence_type(text: str, start: int, end: int) -> str:
    """Classify the evidence span without upgrading ambiguous prose."""
    local=text[max(0,start-160):min(len(text),end+160)]
    for match in _QURAN_RANGE_RE.finditer(text):
        if match.start()<end and match.end()>start:
            cue=text[max(0,match.start()-100):match.start()]
            if re.search(r'قال ﷺ|وقال ﷺ|المصطفى ﷺ|المحبوب ﷺ|قال رسول الله|قال النبي|عن النبي|حديث|قوله صلى',cue):return 'hadith'
            if '﴿' in match.group() or re.search(r'قال تعالى|قوله تعالى|يقول تعالى|قال الله|قوله سبحانه',cue):return 'quran'
    for match in re.finditer(r'[«"“\[\]]([^»"”\[\]]{8,800})[»"”\[\]]',text):
        cue=text[max(0,match.start()-130):match.start()]
        if match.start()<end and match.end()>start and re.search(r'قال رسول الله|قال النبي|عن النبي|روى|رواه|حدثنا|أخبرنا|قوله صلى',cue):return "hadith"
    from app.services.question_search import dialogue_at
    if dialogue_at(text,start):return "dialogue"
    heading = _QASIDA_HEADING_RE.search(text or "")
    if heading and heading.start() < end and heading.end() > start:
        return "heading"
    marker = _FOOTNOTE_SEPARATOR_RE.search(text or "")
    if marker and start >= marker.start():
        return "footnote"
    return "body"


def _highlight(text: str, pattern: re.Pattern) -> tuple[str, int]:
    count = 0

    def _sub(m):
        nonlocal count
        count += 1
        return f"<mark>{m.group(0)}</mark>"

    return pattern.sub(_sub, text), count


@lru_cache(maxsize=32768)
def _match_spans(text: str, pattern: re.Pattern) -> tuple:
    """Cache only immutable text/pattern computations, never corpus identities.

    Changed source bytes or normalization patterns necessarily use a new key.
    No stale book/page results can survive a corpus replacement through this cache.
    """
    return tuple(m.span() for m in pattern.finditer(text))


def _first_match(text: str, pattern: re.Pattern):
    spans = _match_spans(text, pattern)
    return pattern.match(text, spans[0][0]) if spans else None


def _make_snippet(plain_text: str, pattern: re.Pattern, radius: int = 120) -> str:
    """
    Trim a long page down to a window around the first match, THEN
    highlight — never slice already-tagged HTML, which could cut a
    <mark>/</mark> tag in half.
    """
    m = _first_match(plain_text, pattern)
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
        "SELECT book_id, title, page_count, source_grade, source_code, source_tier, "
        "compiler, authorship_mode, attribution_confidence, provenance_status, "
        "canonical_book_id, edition_relation, searchable_by_default "
        "FROM books ORDER BY source_tier, title"
    ).fetchall()
    return [dict(r) | {"searchable_by_default": bool(r["searchable_by_default"])} for r in rows]


def get_book(book_id: str) -> dict | None:
    """Full metadata for one book, including the provenance note."""
    conn = _connection()
    row = conn.execute(
        "SELECT book_id, title, page_count, source_grade, source_code, source_tier, "
        "       source_author, compiler, authorship_mode, attribution_confidence, "
        "       provenance_status, source_note, canonical_book_id, edition_relation, "
        "       searchable_by_default "
        "FROM books WHERE book_id = ?",
        (book_id,),
    ).fetchone()
    return (dict(row) | {"searchable_by_default": bool(row["searchable_by_default"])}) if row else None


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
               p.qasida_number, p.qasida_title, p.qasida_bayt_count,
               p.bayt_from, p.bayt_to,
               p.block_type, p.text,
               b.title AS book_title, b.page_count AS total_pages,
               b.source_grade, b.source_code, b.source_tier,
               b.source_author, b.compiler, b.authorship_mode,
               b.attribution_confidence, b.provenance_status,
               b.canonical_book_id, b.edition_relation,
               b.searchable_by_default
        FROM pages p
        JOIN books b ON b.book_id = p.book_id
        WHERE p.book_id = ? AND p.seq = ?
        """,
        (book_id, seq),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["searchable_by_default"] = bool(d["searchable_by_default"])
    d["qasida_title"] = _concise_qasida_title(d.get("qasida_title"))
    d["content_types"] = content_types(d["text"])
    from app.core.evidence_blocks import blocks
    d["evidence_blocks"] = blocks(d["text"], d["block_type"])
    d.update(citation_metadata(book_id, seq, d["printed_page"]))
    d["has_prev"] = seq > 1
    d["has_next"] = seq < d["total_pages"]
    return d



def citation_metadata(book_id, seq, printed_page):
    repeated = bool(printed_page is not None and _connection().execute(
        "SELECT COUNT(*) FROM pages WHERE book_id=? AND printed_page=?",
        (book_id, printed_page)).fetchone()[0] > 1)
    result={"page_id":f"{book_id}-p{seq}","pagination_status":"repeated_printed_label_unresolved" if repeated else "unique_in_index","pagination_warning":"Printed label repeats; cite by sequence. Original scan review remains pending." if repeated else None}
    if repeated:
        title=_connection().execute("SELECT title FROM books WHERE book_id=?",(book_id,)).fetchone()[0]
        result.update(citation_label=f"{title}، الموضع {book_id}-p{seq}",citation_basis="sequence_only_unreliable_printed_label")
    return result


def _page_texts(keys: Iterable[tuple[str, int]]) -> dict[tuple[str, int], str]:
    """Fetch candidate page text in bounded batches.

    Hybrid ranking used to call ``get_page`` once while scoring and again
    while rendering every candidate.  A broad 500-page pool therefore caused
    roughly one thousand individual SQLite queries.  One batched read keeps
    the same candidate set and ranking semantics without that request fan-out.
    """
    unique = list(dict.fromkeys((str(book_id), int(seq)) for book_id, seq in keys))
    values: dict[tuple[str, int], str] = {}
    conn = _connection()
    for start in range(0, len(unique), 400):
        batch = unique[start:start + 400]
        if not batch:
            continue
        placeholders = ",".join("(?, ?)" for _ in batch)
        params = [value for pair in batch for value in pair]
        rows = conn.execute(
            "SELECT book_id, seq, text FROM pages "
            f"WHERE (book_id, seq) IN ({placeholders})",
            params,
        ).fetchall()
        values.update({(row["book_id"], int(row["seq"])): row["text"] for row in rows})
    return values


# ---------------------------------------------------------------- search

_PROCLITICS = ("وال", "فال", "بال", "كال", "لل", "ال", "و", "ف", "ب", "ل", "ك")
_LEXEME_PREFIXES = ("", "ال", "و", "ف", "ب", "ل", "ك", "وال", "فال", "بال", "كال", "لل")
_LEXEME_SUFFIXES = ("", "ه", "ها", "هم", "هن", "ك", "كم", "كما", "كن", "نا", "يه", "يات")


def _hybrid_safe_tokens(text: str) -> list[str]:
    """Drop discovery stopwords while preserving citation-relevant spelling."""
    values = []
    for word in safe_tokens(text):
        base = word
        # Strip only unambiguous conjunctions.  A blind leading-Waw rule would
        # corrupt lexical words such as وقتها -> قتها.  Definite-article forms
        # (والحقيقة) and attached stopwords (وعدم) are safe to separate.
        if word.startswith(("وال", "فال")) and len(word) > 4:
            base = word[1:]
        elif word.startswith(("و", "ف")) and len(word) > 2:
            candidate = word[1:]
            broad_candidate = normalize_search_text(candidate, level="broad")
            if broad_candidate in ARABIC_STOPWORDS | {"عدم"}:
                base = candidate
        if normalize_search_text(base, level="broad") not in ARABIC_STOPWORDS | {"عدم"}:
            values.append(base)
    return values


def _broad_index_variants(token: str) -> tuple[str, ...]:
    """Spell broad discovery forms against the safe orthographic index."""
    values = {normalize_search_text(token, level="safe")}
    replacements = {
        "ه": ("ه", "ة"),
        "ي": ("ي", "ى"),
        "ا": ("ا", "أ", "إ", "آ"),
    }
    # Expand one position at a time to avoid an exponential query explosion.
    seed = next(iter(values))
    for index, char in enumerate(seed):
        for replacement in replacements.get(char, ()):
            values.add(seed[:index] + replacement + seed[index + 1:])
    return tuple(sorted(value for value in values if value))


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


# Versioned lookup projects broad discovery forms onto spellings actually in
# the safe index. Unlike one-character inversion, this preserves combinations
# (for example both hamza and taa marbuta in طمأنينة) without guessed roots.
LEXEME_POLICY_VERSION = "safe-vocabulary-union-v1"

@lru_cache(maxsize=2)
def _indexed_spellings(path: str, mtime_ns: int, size: int) -> dict[str, tuple[str, ...]]:
    forms: dict[str, set[str]] = {}
    tokens = set()
    for row in _connection().execute("SELECT norm_text FROM pages"):
        tokens.update(row[0].split())
    for token in tokens:
        forms.setdefault(normalize_search_text(token, level="broad"), set()).add(token)
    return {key: tuple(sorted(value)) for key, value in forms.items()}


def _lexeme_index_forms(query: str) -> list[str]:
    path = os.path.abspath(get_settings().library_db_path)
    stat = os.stat(path)
    vocabulary = _indexed_spellings(path, stat.st_mtime_ns, stat.st_size)
    words = safe_tokens(query)
    if len(words) != 1:
        raise ValueError("lexeme search supports one Arabic word per query")
    forms = set(safe_term_variants(words[0]))
    for stem in _lexeme_stems(words[0]):
        for prefix in _LEXEME_PREFIXES:
            for suffix in _LEXEME_SUFFIXES:
                key = normalize_search_text(prefix + stem + suffix, level="broad")
                forms.update(vocabulary.get(key, ()))
    return sorted(forms)


def _query_expression(query: str, search_mode: str = "exact_phrase") -> str:
    # Literal modes use the safe index and preserve hamza, ى/ي and ة/ه.
    # Lexeme/hybrid expansion may generate broader candidates later, but it is
    # always labelled as non-literal evidence.
    normalized = normalize_search_text(query, level="safe")
    if not normalized:
        return ""
    if search_mode=='exact_phrase':normalized=re.sub(r'\bو\s+(?=[ء-ي])','و',normalized)
    words = [w for w in normalized.split() if w]
    if search_mode == "lexeme":
        if len(words) != 1:
            raise ValueError("lexeme search supports one Arabic word per query")
        variants = _lexeme_index_forms(query)
        return " OR ".join('"' + v.replace('"', '""') + '"' for v in variants)
    if search_mode == "exact_phrase":
        # FTS token boundaries make معرفة and المعرفة distinct. Search both
        # definite and indefinite forms so exact mode does not silently lose
        # matches merely because the article is attached.
        choices = []
        for word in words:
            variants = set(conjunction_variants(safe_term_variants(word)))
            choices.append(sorted(variants))
        if len(choices) > 8:
            # A broad FTS gate only; original-text phrase validation below is
            # authoritative for both retrieval and census.
            return " AND ".join("(" + " OR ".join('"' + v.replace('"', '""') + '"' for v in group) + ")" for group in choices)
        phrases = [" ".join(parts) for parts in product(*choices)]
        return " OR ".join('"' + phrase.replace('"', '""') + '"' for phrase in phrases)
    if search_mode == "all_words":
        content_words = safe_tokens(query, drop_stopwords=True) or words
        groups = []
        for word in content_words:
            variants = safe_term_variants(word)
            groups.append("(" + " OR ".join(
                '"' + v.replace('"', '""') + '"' for v in variants
            ) + ")")
        return " AND ".join(groups)
    if search_mode == "any_word":
        return " OR ".join('"' + w.replace('"', '""') + '"' for w in words)
    raise ValueError("search_mode must be exact_phrase, all_words, any_word, or lexeme")


@lru_cache(maxsize=2048)
def _pattern_for_query(
    query: str, search_mode: str, *, whole_word: bool = True,
) -> re.Pattern:
    if search_mode == "exact_phrase":
        return _build_exact_variant_regex(query, whole_word=whole_word)
    if search_mode != "lexeme":
        return _build_highlight_regex(query, whole_word=whole_word)
    normalized = normalize_arabic(query, aggressive=True)
    words = normalized.split()
    if len(words) != 1:
        raise ValueError("lexeme search supports one Arabic word per query")
    stems = _lexeme_stems(words[0])
    stem_patterns = []
    for stem in stems:
        chars = [_tolerant_char_pattern(c, normalization_level="broad") for c in stem]
        stem_patterns.append(_DIACRITIC_CLASS.join(chars) + _DIACRITIC_CLASS)
    def word_pattern(word: str) -> str:
        return _DIACRITIC_CLASS.join(
            _tolerant_char_pattern(c, normalization_level="broad") for c in word
        ) + _DIACRITIC_CLASS
    prefix_patterns = [word_pattern(p) for p in _LEXEME_PREFIXES if p]
    suffix_patterns = [word_pattern(s) for s in _LEXEME_SUFFIXES if s]
    prefix = "(?:" + "|".join(prefix_patterns) + ")?"
    suffix = "(?:" + "|".join(suffix_patterns) + ")?"
    start_boundary = rf"(?<!{_ARABIC_BOUNDARY})" if whole_word else ""
    boundary = rf"(?!{_ARABIC_BOUNDARY})" if whole_word else ""
    broad = start_boundary + prefix + "(?:" + "|".join(stem_patterns) + ")" + suffix + boundary
    literal = _build_exact_variant_regex(query, whole_word=whole_word).pattern
    return re.compile("(?:" + literal + "|" + broad + ")", re.IGNORECASE)



def _unique_occurrence_count(text: str, patterns: list[re.Pattern]) -> int:
    return len({span for pattern in patterns for span in _match_spans(text, pattern)})


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
    qasida_number=None, min_tier=None,
) -> tuple[str, list]:
    sql, params = "", []
    if book_ids:
        placeholders = ",".join("?" for _ in book_ids)
        sql += f" AND p.book_id IN ({placeholders})"
        params.extend(book_ids)
    else:
        # Non-canonical editions remain directly searchable by explicit ID or
        # exact title scope, but must not duplicate hits and occurrence counts
        # in an ordinary whole-library search.
        sql += " AND b.searchable_by_default = 1"
    if source_code:
        sql += " AND b.source_code = ?"
        params.append(source_code)
    if min_tier is not None:
        # Lower tier numbers have greater authority. ``min_tier=2`` therefore
        # means "accept tier 1 or 2", matching the scholarly use case.
        sql += " AND b.source_tier <= ?"
        params.append(int(min_tier))
    if page_from is not None:
        sql += " AND p.seq >= ?"
        params.append(page_from)
    if page_to is not None:
        sql += " AND p.seq <= ?"
        params.append(page_to)
    if qasida_number is not None:
        sql += " AND p.qasida_number = ?"
        params.append(qasida_number)
    from app.core.evidence_blocks import INCLUDE_TOC
    if not INCLUDE_TOC.get():
        sql += " AND p.block_type != 'toc'"
    return sql, params


def _matching_page_ids(queries, operator="OR", search_mode="exact_phrase", whole_word=True, **scope):
    """Eligible source identities, before ranking, thresholds or pagination."""
    expression = _fts_expression(queries, operator, search_mode)
    if not expression:
        return set()
    filters, params = _search_filters(**scope)
    rows = _connection().execute(
        "SELECT p.book_id,p.seq,p.text FROM pages_fts "
        "JOIN pages p ON p.id=pages_fts.rowid JOIN books b ON b.book_id=p.book_id "
        "WHERE pages_fts MATCH ?" + filters, [expression, *params],
    )
    patterns = [_pattern_for_query(q, search_mode, whole_word=whole_word) for q in queries]
    identities = set()
    for row in rows:
        if search_mode in {"exact_phrase", "lexeme"}:
            text = _indexable_text(row["text"])
            flags = [bool(_match_spans(text, p)) for p in patterns]
            if not (all(flags) if operator == "AND" else any(flags)):
                continue
        identities.add((row["book_id"], row["seq"]))
    return identities


def literal_inclusion_report(queries, candidate_ids, *, operator="OR", whole_word=True, **scope):
    """Compare identities: equal counts cannot conceal substituted pages."""
    literal = _matching_page_ids(queries, operator, whole_word=whole_word, **scope)
    missing = literal - set(candidate_ids)
    return {
        "literal_pages": len(literal), "candidate_pages": len(candidate_ids),
        "missing_literal_pages": len(missing),
        "missing_literal_page_sample": [f"{book}-p{seq}" for book, seq in sorted(missing)[:20]],
        "status": "warning" if missing else "ok",
        "scope": "eligible_pages_before_ranking_score_filter_and_pagination",
    }


@profiled("completeness_audit")
def retrieval_completeness(queries, search_mode, *, operator="OR", whole_word=True,
                           candidate_ids=None, per_query_candidates=None, **scope):
    actual = candidate_ids is not None
    candidates = (set(candidate_ids) if actual else
                  _matching_page_ids(queries, operator, search_mode, whole_word, **scope))
    report = literal_inclusion_report(queries, candidates, operator=operator, whole_word=whole_word, **scope)
    report["method"] = "actual_retrieved_candidates" if actual else "independent_index_candidate_check"
    report["per_query"] = []
    for query in queries:
        ids = (set((per_query_candidates or {}).get(query, candidates)) if actual else
               _matching_page_ids([query], "OR", search_mode, whole_word, **scope))
        # An AND result need only contain pages eligible for the full conjunction.
        # Pages satisfying only one alternative are not omissions.
        if actual and operator.upper() == "AND":
            item = literal_inclusion_report(queries, ids, operator="AND", whole_word=whole_word, **scope)
        else:
            item = literal_inclusion_report([query], ids, whole_word=whole_word, **scope)
        report["per_query"].append({"query": query, **item})
    report["per_query_scope"] = "combined_AND_eligibility" if operator.upper() == "AND" else "individual_query_eligibility"
    if any(item["status"] == "warning" for item in report["per_query"]):
        report["status"] = "warning"
    return report


def count_search(
    queries: list[str], operator: str = "OR", book_ids: list[str] | None = None,
    source_code: str | None = None, page_from: int | None = None,
    page_to: int | None = None, search_mode: str = "exact_phrase",
    qasida_number: int | None = None, min_tier: int | None = None,
    count_basis: str = "phrase", whole_word: bool = True,
) -> int:
    """Return the census page count under an explicit, mode-independent basis."""
    return int(search_stats(
        queries, operator=operator, book_ids=book_ids, source_code=source_code,
        page_from=page_from, page_to=page_to, qasida_number=qasida_number,
        min_tier=min_tier, count_basis=count_basis, whole_word=whole_word,
    )["matching_pages"])


@profiled("literal_census")
@__import__("app.core.census_cache",fromlist=["cached_census"]).cached_census
def search_stats(
    queries: list[str], operator: str = "OR", book_ids: list[str] | None = None,
    source_code: str | None = None, page_from: int | None = None,
    page_to: int | None = None, search_mode: str = "exact_phrase",
    qasida_number: int | None = None, min_tier: int | None = None,
    count_basis: str = "phrase", whole_word: bool = True,
) -> dict:
    """Return a token-anchored census independent of the retrieval mode.

    ``search_mode`` remains accepted for API compatibility but does not decide
    what is counted. Callers choose ``count_basis=phrase`` or ``term_bag``.
    """
    if count_basis not in {"phrase", "term_bag"}:
        raise ValueError("count_basis must be phrase or term_bag")
    count_mode = "exact_phrase" if count_basis == "phrase" else "all_words"
    expression = _fts_expression(queries, operator, count_mode)
    if not expression:
        return {
            "matching_pages": 0, "normalized_occurrences": 0,
            "surface_occurrences": 0, "matching_occurrences": 0,
            "count_basis": count_basis, "whole_word": bool(whole_word),
            "normalization_level": "safe", "footnotes_excluded": True,
            "per_query": [],
        }
    filters, params = _search_filters(
        book_ids=book_ids, source_code=source_code,
        page_from=page_from, page_to=page_to, qasida_number=qasida_number,
        min_tier=min_tier,
    )
    sql = """SELECT p.id, p.text FROM pages_fts
             JOIN pages p ON p.id = pages_fts.rowid
             JOIN books b ON b.book_id = p.book_id
             WHERE pages_fts MATCH ?""" + filters
    rows = _connection().execute(sql, [expression, *params]).fetchall()
    if count_basis == "phrase":
        def eligible(row, qs, op):
            flags = [bool(_pattern_for_query(q, "exact_phrase", whole_word=whole_word).search(_indexable_text(row["text"]))) for q in qs]
            return all(flags) if op == "AND" else any(flags)
        rows = [r for r in rows if eligible(r, queries, operator)]
    if count_basis == "phrase":
        aggregate_patterns = [
            _pattern_for_query(q, "exact_phrase", whole_word=whole_word)
            for q in queries
        ]
    else:
        aggregate_patterns = _term_highlight_patterns(
            queries, whole_word=whole_word,
        )
    per_query = []
    for query in queries:
        q_expression = _fts_expression([query], "OR", count_mode)
        q_rows = _connection().execute(sql, [q_expression, *params]).fetchall()
        if count_basis == "phrase":
            q_rows = [r for r in q_rows if eligible(r, [query], "OR")]
        q_patterns = (
            [_pattern_for_query(query, "exact_phrase", whole_word=whole_word)]
            if count_basis == "phrase"
            else _term_highlight_patterns([query], whole_word=whole_word)
        )
        surface_pattern = _build_highlight_regex(
            query, whole_word=whole_word, normalization_level="surface",
        )
        per_query.append({
            "query": query,
            "matching_pages": len(q_rows),
            "normalized_occurrences": sum(
                _unique_occurrence_count(_indexable_text(r["text"]), q_patterns)
                for r in q_rows
            ),
            "surface_occurrences": sum(
                _unique_occurrence_count(_indexable_text(r["text"]), [surface_pattern])
                for r in q_rows
            ),
            "count_basis": count_basis,
        })
        per_query[-1]["occurrences"] = per_query[-1]["normalized_occurrences"]
    normalized_occurrences = sum(
        _unique_occurrence_count(_indexable_text(r["text"]), aggregate_patterns)
        for r in rows
    )
    surface_occurrences = sum(
        sum(_unique_occurrence_count(
            _indexable_text(r["text"]),
            [_build_highlight_regex(q, whole_word=whole_word, normalization_level="surface")],
        ) for q in queries)
        for r in rows
    )
    return {
        "matching_pages": len(rows),
        "normalized_occurrences": normalized_occurrences,
        "surface_occurrences": surface_occurrences,
        # Compatibility alias; unlike the old field its polarity is explicit.
        "matching_occurrences": normalized_occurrences,
        "count_basis": count_basis,
        "whole_word": bool(whole_word),
        "normalization_level": "safe",
        "footnotes_excluded": True,
        "per_query": per_query,
    }


def _ranking_order(ranking: str, diversified: bool = False) -> str:
    """Return deterministic SQL ordering with unambiguous column names."""
    book = "book_id" if diversified else "p.book_id"
    seq = "seq" if diversified else "p.seq"
    title = "book_title" if diversified else "b.title"
    source = "source_code" if diversified else "b.source_code"
    block = "block_type" if diversified else "p.block_type"
    tier = "source_tier" if diversified else "b.source_tier"
    structural = f"CASE WHEN {block} = 'toc' THEN 1 ELSE 0 END"
    if ranking == "relevance":
        return f"{structural}, relevance, {title}, {book}, {seq}"
    if ranking == "primary_first":
        body_factor = f"CASE WHEN {block} = 'toc' THEN 0.15 ELSE 1.0 END"
        bounded = "CASE WHEN -relevance > 0 THEN (-relevance)/((-relevance)+5.0) ELSE 0.0 END"
        source_boost = f"CASE WHEN {source} = 'primary' THEN 0.05 ELSE 0.0 END"
        tier_boost = f"(6 - {tier}) * 0.01"
        rank_score = f"(({body_factor}) * ({bounded}) + ({source_boost}) + ({tier_boost}))"
        return f"{rank_score} DESC, {structural}, relevance, {title}, {book}, {seq}"
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
    text: str, term_groups: list[tuple[str, ...]], *,
    normalization_level: str = "broad",
) -> tuple[float, int, int]:
    """Return calibrated relevance and the smallest original-text term span."""
    if not term_groups:
        return (0.0, 0, 0)
    text = _indexable_text(text)
    occurrences: list[tuple[int, int, int]] = []
    for group_index, variants in enumerate(term_groups):
        seen: set[tuple[int, int]] = set()
        for variant in variants:
            for span in _match_spans(text, _build_highlight_regex(
                variant, whole_word=True, normalization_level=normalization_level,
            )):
                if span not in seen:
                    occurrences.append((*span, group_index))
                    seen.add(span)
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


def _all_query_terms(raw_queries: list[str]) -> list[tuple[str, str]]:
    """Return every Arabic query token, including citation-relevant particles."""
    return [
        (match.group(0), normalize_arabic(match.group(0), aggressive=True))
        for query in raw_queries
        for match in _ARABIC_TOKEN_RE.finditer(query)
    ]


def _surface_key(value: str) -> str:
    """Compare visible spelling while ignoring only tashkil and tatweel."""
    return strip_diacritics(remove_tatweel(value))


def _ya_comparison_stem(value: str) -> str:
    """Remove an attached article/proclitic only for ى/ي comparison."""
    for prefix in _COMPARISON_PREFIXES:
        if value.startswith(prefix) and len(value) - len(prefix) >= 2:
            return value[len(prefix):]
    return value


def _term_evidence(
    display: str, normalized: str, corpus_form: str, relation: str,
) -> dict[str, str]:
    item = {
        "corpus_form": corpus_form,
        "surface_form": corpus_form,
        "normalized_form": normalize_arabic(corpus_form, aggressive=True),
        "safe_normalized_form": normalize_search_text(corpus_form, level="safe"),
        "query_normalized": normalized,
        "relation": relation,
    }
    # Warn only when ى/ي normalization itself explains the surface mismatch.
    # The old condition warned on unrelated differences (for example a
    # definite article) whenever both words happened to contain ي.
    query_surface = _ya_comparison_stem(_surface_key(display))
    corpus_surface = _ya_comparison_stem(_surface_key(corpus_form))
    ya_variants = set("ىيیے")
    if (
        query_surface != corpus_surface
        and bool((set(query_surface) | set(corpus_surface)) & ya_variants)
        and normalize_ya(query_surface) == normalize_ya(corpus_surface)
    ):
        item["normalization_warning"] = "ى/ي ambiguity; surface_form is authoritative"
    query_safe = normalize_search_text(display, level="safe")
    corpus_safe = normalize_search_text(corpus_form, level="safe")
    if (
        query_safe != corpus_safe
        and normalize_search_text(display, level="broad")
        == normalize_search_text(corpus_form, level="broad")
    ):
        item["normalization_warning"] = (
            "broad normalization collapsed a distinct Arabic form; "
            "surface_form is authoritative and this is not literal evidence"
        )
    return item


def _term_highlight_patterns(
    raw_queries: list[str], *, whole_word: bool = True,
) -> list[re.Pattern]:
    """Build non-root, article-aware patterns for strict term evidence."""
    patterns: list[re.Pattern] = []
    seen: set[str] = set()
    for query in raw_queries:
        for display in safe_tokens(query, drop_stopwords=True):
            normalized = normalize_search_text(display, level="safe")
            variants = sorted(set(safe_term_variants(normalized)), key=len, reverse=True)
            pattern = re.compile(
                "(?:" + "|".join(
                    _build_highlight_regex(v, whole_word=whole_word).pattern
                    for v in variants
                ) + ")",
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
    pools = [evidence_text]
    evidence: dict[str, dict[str, str]] = {}
    for query in raw_queries:
      for display in safe_tokens(query, drop_stopwords=True):
        normalized = normalize_search_text(display, level="safe")
        allowed = set(safe_term_variants(normalized))
        for pool in pools:
            corpus_tokens = [
                match.group(0) for match in _ARABIC_TOKEN_RE.finditer(pool)
            ]
            for corpus_form in corpus_tokens:
                corpus_normalized = normalize_search_text(corpus_form, level="safe")
                if corpus_normalized not in allowed:
                    continue
                same_form = _surface_key(corpus_form) == _surface_key(display)
                evidence[display] = _term_evidence(
                    display, normalized, corpus_form,
                    "exact" if same_form else "normalized",
                )
                break
            if display in evidence:
                break
    return evidence


def _matched_literal_terms(
    text: str, raw_queries: list[str], start: int, end: int,
) -> dict[str, dict[str, str]]:
    """Expose authoritative surface spelling for exact/any-term evidence."""
    evidence_text = text[start:end] if end > start else text
    corpus_tokens = [m.group(0) for m in _ARABIC_TOKEN_RE.finditer(evidence_text)]
    normalized_corpus = [normalize_search_text(t, level="safe") for t in corpus_tokens]
    evidence: dict[str, dict[str, str]] = {}
    lookup = _literal_term_lookup(tuple(raw_queries))
    for corpus_form, corpus_normalized in zip(corpus_tokens, normalized_corpus):
        for display, normalized in lookup.get(corpus_normalized, ()):
            if display in evidence:
                continue
            relation = "exact" if _surface_key(corpus_form) == _surface_key(display) else ("article_variant" if corpus_normalized != normalized and corpus_normalized.removeprefix('ال') == normalized.removeprefix('ال') else "normalized")
            evidence[display] = _term_evidence(
                display, normalized, corpus_form, relation,
            )
    # Phrase-level spacing is declared separately from per-token evidence.
    for query in raw_queries:
        if re.sub(r'\bو\s+(?=[ء-ي])','و',normalize_search_text(evidence_text)) == re.sub(r'\bو\s+(?=[ء-ي])','و',normalize_search_text(query)) and normalize_search_text(evidence_text)!=normalize_search_text(query):
            evidence[query]=_term_evidence(query,normalize_search_text(query),evidence_text,'detached_conjunction')
    return evidence


@lru_cache(maxsize=512)
def _literal_term_lookup(queries: tuple[str, ...]) -> dict:
    lookup = {}
    for query in queries:
        for display in safe_tokens(query):
            normalized = normalize_search_text(display, level="safe")
            for variant in safe_term_variants(normalized):
                lookup.setdefault(variant, []).append((display, normalized))
    return lookup


def _matched_lexeme(text: str, raw_query: str) -> dict[str, dict[str, str]]:
    """Explain the surface form and relation used by a one-word lexeme hit."""
    # Lexeme is an explicit one-word request; even a function word is evidence
    # and must not disappear through the hybrid stopword policy.
    query_terms = _all_query_terms([raw_query])
    if len(query_terms) != 1:
        return {}
    display, normalized = query_terms[0]
    match = _pattern_for_query(raw_query, "lexeme").search(text)
    if not match:
        return {}
    corpus_form = match.group(0)
    corpus_normalized = normalize_arabic(corpus_form, aggressive=True)
    if _surface_key(corpus_form) == _surface_key(display):
        relation = "exact"
    elif normalize_search_text(corpus_form, level="safe") in set(
        safe_term_variants(normalize_search_text(display, level="safe"))
    ):
        relation = "safe_normalized"
    elif corpus_normalized == normalized:
        relation = "broad_normalized"
    elif corpus_normalized in set(term_variants(normalized)):
        relation = "inflection"
    else:
        relation = "root" if lexical_root(normalized) else "inflection"
    item = _term_evidence(display, normalized, corpus_form, relation)
    root = lexical_root(normalized)
    if relation == "root" and root:
        item["root"] = root
    return {display: item}


def _matched_hybrid_terms(
    text: str, raw_queries: list[str], start: int, end: int,
) -> dict[str, dict[str, str]]:
    """Explain every content token supporting a hybrid evidence window.

    Hybrid may use curated derivational relatives, so its evidence relation
    is allowed to be ``root`` or ``concept``.  This function never upgrades
    those relations to literal evidence and always preserves the corpus form.
    """
    evidence_text = text[start:end] if end > start else text
    corpus_tokens = [m.group(0) for m in _ARABIC_TOKEN_RE.finditer(evidence_text)]
    normalized_corpus = [normalize_arabic(t, aggressive=True) for t in corpus_tokens]
    evidence: dict[str, dict[str, str]] = {}
    for display, normalized in _content_query_terms(raw_queries):
        variants = set(lexical_variants(normalized))
        strict_variants = set(term_variants(normalized))
        for corpus_form, corpus_normalized in zip(corpus_tokens, normalized_corpus):
            if corpus_normalized not in variants:
                continue
            if _surface_key(corpus_form) == _surface_key(display):
                relation = "exact"
            elif normalize_search_text(corpus_form, level="safe") in set(
                safe_term_variants(normalize_search_text(display, level="safe"))
            ):
                relation = "safe_normalized"
            elif corpus_normalized in strict_variants:
                relation = "broad_normalized"
            elif lexical_root(normalized):
                relation = "root"
            else:
                relation = "concept"
            item = _term_evidence(display, normalized, corpus_form, relation)
            root = lexical_root(normalized)
            if relation == "root" and root:
                item["root"] = root
            evidence[display] = item
            break
    return evidence


def _bayt_at_offset(text: str, offset: int, qasida_number: int | None) -> tuple[int | None, str | None]:
    if qasida_number is None:
        return (None, None)
    markers = list(_BAYT_MARKER_RE.finditer(text))
    preceding = [m for m in markers if m.start() <= offset]
    if not preceding:
        return (None, None)
    number = int(preceding[-1].group(1))
    return (number, f"b14-q{qasida_number:03d}-b{number:03d}")


def _structural_identity(
    text: str, start: int, end: int, qasida_number: int | None,
    qasida_bayt_count: int | None = None,
) -> dict[str, object]:
    """Return a stable qasida container and bayt identity for an evidence span."""
    if qasida_number is None:
        return {}
    identity: dict[str, object] = {"container_id": f"b14-q{qasida_number:03d}"}
    if qasida_bayt_count is not None:
        identity["qasida_bayt_count"] = int(qasida_bayt_count)
    start_number, start_id = _bayt_at_offset(text, start, qasida_number)
    end_number, end_id = _bayt_at_offset(text, max(start, end - 1), qasida_number)
    if start_number is None:
        heading = _QASIDA_HEADING_RE.search(text)
        if heading and start < heading.end() and end > heading.start():
            heading_id = f"b14-q{qasida_number:03d}-h"
            identity.update({
                "stable_id": heading_id,
                "stable_id_kind": "qasida_heading",
                "heading_id": heading_id,
            })
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
    min_tier: int | None = None,
    whole_word: bool = True,
    _audit_candidates: bool = False,
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
        min_tier=min_tier,
    )

    requested_limit, requested_offset = limit, offset
    requested_min = max(0.0, min(float(min_score or 0.0), 1.0))
    from app.core.evidence_blocks import INCLUDE_TOC, block_at
    terms_pool = True  # Final scoring precedes pagination, including TOC penalties.
    needs_post_filter = terms_pool or requested_min > 0.0
    if terms_pool:
        sql_limit = int(conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0])
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
               b.source_tier, b.canonical_book_id, b.edition_relation,
               b.source_author, b.compiler, b.authorship_mode,
               b.attribution_confidence, b.provenance_status,
               b.searchable_by_default, p.seq, p.printed_page, p.citation_label,
               p.qasida_number, p.qasida_title, p.qasida_bayt_count,
               p.bayt_from, p.bayt_to,
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
    phase_started = perf_counter()
    rows = conn.execute(sql, params).fetchall()
    record_phase("candidate_sql", phase_started)
    phase_started = perf_counter()

    patterns = [
        _pattern_for_query(q.strip(), search_mode, whole_word=whole_word)
        for q in raw_queries if q and q.strip()
    ]
    term_patterns = (
        _term_highlight_patterns(raw_queries, whole_word=whole_word)
        if search_mode == "all_words" else []
    )
    results = []
    query_candidates = {q: set() for q in raw_queries}
    for row in rows:
        from app.core.budget import check
        check()
        source_text = row["text"]
        plain_text = _indexable_text(source_text)
        if row["block_type"] == "toc" and not INCLUDE_TOC.get():
            continue
        matches = [(_first_match(plain_text, pat), pat) for pat in patterns]
        matches = [(m, pat) for m, pat in matches if m]
        if search_mode in {"exact_phrase", "lexeme"} and (
            not matches or (operator.upper() == "AND" and len(matches) != len(patterns))
        ):
            # The FTS candidate and public evidence matcher must agree. Never
            # fabricate an occurrence/snippet from an unmatched candidate.
            continue
        if matches:
            _, pattern = min(matches, key=lambda x: x[0].start())
            occ = _unique_occurrence_count(plain_text, patterns)
            snippet = _make_snippet(plain_text, pattern, radius=context_chars)
        else:
            occ = 0
            snippet = _esc(plain_text[: context_chars * 2])
            if len(plain_text) > context_chars * 2:
                snippet += "…"

        label = f"الصفحة {row['printed_page']}" if row["printed_page"] else f"المقطع {row['seq']}"
        result = {
            "book_id": row["book_id"], "book_title": row["book_title"],
            "source_grade": row["source_grade"], "source_code": row["source_code"],
            "source_tier": row["source_tier"],
            "source_author": row["source_author"],
            "compiler": row["compiler"],
            "authorship_mode": row["authorship_mode"],
            "attribution_confidence": row["attribution_confidence"],
            "provenance_status": row["provenance_status"],
            "canonical_book_id": row["canonical_book_id"],
            "edition_relation": row["edition_relation"],
            "searchable_by_default": bool(row["searchable_by_default"]),
            "seq": row["seq"], "page_number": row["seq"], "page_label": label,
            "printed_page": row["printed_page"], "occurrences": occ,
            "citation_label": row["citation_label"],
            "qasida_number": row["qasida_number"],
            "qasida_title": _concise_qasida_title(row["qasida_title"]),
            "qasida_bayt_count": row["qasida_bayt_count"],
            "bayt_from": row["bayt_from"], "bayt_to": row["bayt_to"],
            "page_bayt_from": row["bayt_from"],
            "page_bayt_to": row["bayt_to"],
            "bayt_range_scope": "page" if row["bayt_from"] is not None else None,
            "block_type": row["block_type"],
            "snippet": snippet,
            "_raw_relevance": -float(row["relevance"]),
            "match_type": {
                "exact_phrase": "exact", "all_words": "terms",
                "any_word": "terms", "lexeme": "lexeme",
            }[search_mode],
        }
        selected = min((m for m, _ in matches), key=lambda m: (m.start(), m.end()), default=None)
        first_match = selected.start() if selected else 0
        if search_mode == "all_words":
            alternatives = [[q] for q in raw_queries] if operator.upper() == "OR" else [raw_queries]
            spans = []
            for alternative in alternatives:
                groups = [safe_term_variants(w) for q in alternative
                          for w in (safe_tokens(q, drop_stopwords=True) or safe_tokens(q))]
                candidate = _minimum_covering_span(plain_text, groups, normalization_level="safe")
                spans.append((*candidate, alternative))
            local_score, span_start, span_end, selected_queries = max(spans, key=lambda x: (x[0], -x[1]))
            first_match = span_start
            evidence_end = span_end
            result["_local_score"] = local_score
            result["occurrences"] = _unique_occurrence_count(plain_text, term_patterns)
            result["matched_terms"] = _matched_terms(
                plain_text, selected_queries, span_start, span_end,
            )
            if span_end > span_start:
                result["snippet"] = _evidence_excerpt(
                    plain_text, span_start, span_end, context_chars, term_patterns,
                )
        elif search_mode == "lexeme" and raw_queries:
            evidence_end = selected.end() if selected else first_match + 1
            result["matched_terms"] = {}
            for raw_query, pat in zip(raw_queries, patterns):
                local = pat.fullmatch(plain_text[first_match:evidence_end])
                if local:
                    result["matched_terms"].update(_matched_lexeme(local.group(0), raw_query))
            result["selected_queries"] = sorted(result["matched_terms"])
            result["match_attribution_scope"] = "selected_evidence_span"
        else:
            evidence_end = selected.end() if selected else first_match + 1
            result["matched_terms"] = _matched_literal_terms(
                plain_text, raw_queries, first_match, evidence_end,
            )
        result["evidence_type"] = evidence_type(
            source_text, first_match, evidence_end,
        )
        result["block_type"] = block_at(source_text, first_match, row["block_type"])
        result.update(citation_metadata(row["book_id"], row["seq"], row["printed_page"]))
        result["evidence_type_scope"] = "start_anchor"
        result["evidence_type"] = evidence_type(source_text, first_match, first_match + 1)
        result["evidence_type_method"] = "heuristic"
        result["evidence_type_confidence"] = "unverified"
        result["whole_word"] = bool(whole_word)
        result["normalization_level"] = (
            "broad_discovery" if search_mode == "lexeme" else "safe"
        )
        result["footnotes_excluded"] = True
        if row["book_id"] == "b14":
            result.update(_structural_identity(
                plain_text, first_match, evidence_end, row["qasida_number"],
                row["qasida_bayt_count"],
            ))
        result["match_id"] = f"{row['book_id']}-p{row['seq']}-c{first_match}"
        result["evidence_span"] = {
            "start": first_match,
            "end": evidence_end,
            "excerpt": result["snippet"],
        }
        if include_full_text:
            safe_text = _esc(source_text)
            for pattern in patterns:
                safe_text, _ = _highlight(safe_text, pattern)
            result["highlight"] = safe_text
            result["text"] = source_text
        results.append(result)
        if _audit_candidates:
            for q, pat in zip(raw_queries, patterns):
                terms = safe_tokens(q, drop_stopwords=True) if search_mode == "all_words" else []
                term_match = bool(terms) and all(_match_spans(plain_text,
                    _build_exact_variant_regex(t,whole_word=whole_word)) for t in terms)
                if _match_spans(plain_text, pat) or term_match:
                    query_candidates[q].add((row["book_id"], row["seq"]))
    if _audit_candidates:
        record_candidates(((r["book_id"], r["seq"]) for r in results), query_candidates)
    record_phase("evidence_validation", phase_started)
    phase_started = perf_counter()
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
        if ranking == "primary_first":
            _set_rank_score(item)
    if terms_pool or search_mode == "all_words":
        if ranking in {"book_order", "chronological"}:
            results.sort(key=lambda item: (item["book_id"], item["seq"]))
        elif ranking == "primary_first":
            results.sort(key=primary_first_sort_key)
        else:
            results.sort(key=lambda item: (
                -item["score"],
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
    record_phase("ranking_and_pagination", phase_started)
    for rank, item in enumerate(results, start=requested_offset + 1):
        item["rank"] = rank
    return results


@profiled("hybrid_total")
def hybrid_search(**kwargs) -> list[dict]:
    """Local hybrid lexical retrieval using reciprocal-rank fusion.

    The exact phrase, all-terms and any-term signals complement one another:
    exact wording receives the strongest vote while concept-like queries still
    recover pages whose words are separated.  This remains fully local and
    deterministic; an external embedding service is therefore not required at
    request time.
    """
    raw_queries = kwargs.get("queries") or ([kwargs.get("query")] if kwargs.get("query") else [])
    queries = list(raw_queries)
    filtered_queries = []
    for query in queries:
        words = _hybrid_safe_tokens(query)
        if words:
            filtered_queries.append(" ".join(words))
    queries = filtered_queries or queries
    limit = int(kwargs.get("limit", 10))
    offset = int(kwargs.get("offset", 0))
    # Keep a broad enough lexical pool that restoring falsely penalized body
    # pages cannot crowd known relevant evidence out before local scoring.
    # Common Arabic concepts can place a relevant multi-term page hundreds of
    # rows down an OR candidate list.  Keep candidate recall high, then let the
    # local covering-span scorer restore precision.  The corpus is small enough
    # that this remains comfortably bounded.
    configured_pool = int(getattr(get_settings(), "hybrid_candidate_pool", 250))
    pool = min(max((offset + limit) * 20, configured_pool), 1000)
    rrf_scores: dict[tuple[str, int], float] = {}
    mode_scores: dict[tuple[str, int], dict[str, float]] = {}
    records: dict[tuple[str, int], dict] = {}
    # Candidate generation stays page-level (the shipped index has pages), but
    # final co-occurrence is measured in overlapping local chunks.
    query_group_sets = [
        [lexical_variants(word) for word in query.split()]
        for query in queries if query.strip()
    ]
    term_groups = [group for groups in query_group_sets for group in groups]
    # OR alternatives are independently sufficient.  Previously all terms
    # from every alternative were required in one local span, which silently
    # turned an OR request into an AND during final hybrid scoring.
    scoring_group_sets = (
        query_group_sets
        if str(kwargs.get("operator", "OR")).upper() == "OR"
        else [term_groups]
    )
    concept_queries = sorted({
        spelling
        for group in term_groups
        for variant in group
        for spelling in _broad_index_variants(variant)
    })
    for mode, weight in (("exact_phrase", 1.0), ("all_words", 0.8), ("any_word", 0.2)):
        call = dict(kwargs)
        call.update(search_mode=mode, limit=1000000 if mode == "exact_phrase" else pool, offset=0, diversify_books=False)
        # Hybrid records its actual combined pool below; do not turn its broad
        # any-term discovery pool into an unbounded evidence-rendering pass.
        call["_audit_candidates"] = False
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
    record_candidates(records.keys())
    page_texts = _page_texts(records)
    chunk_starts: dict[tuple[str, int], int] = {}
    chunk_ends: dict[tuple[str, int], int] = {}
    local_scores: dict[tuple[str, int], float] = {}
    for key in records:
        text = page_texts.get(key)
        candidates = (
            [_minimum_covering_span(text, groups) for groups in scoring_group_sets]
            if text else [(0.0, 0, 0)]
        )
        best, chunk_start, chunk_end = max(candidates, key=lambda item: item[0])
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
        if row.get("block_type") == "toc":
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
        for key in ordered:
            records[key]["score"] = calibrated_scores[key]
        ordered.sort(key=lambda key: primary_first_sort_key(records[key]))
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
            "(?:" + "|".join(
                _build_highlight_regex(
                    v, whole_word=True, normalization_level="broad",
                ).pattern for v in group
            ) + ")",
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
        page_text = page_texts.get(key)
        if page_text is not None:
            row["snippet"] = _evidence_excerpt(
                page_text, chunk_starts[key], chunk_ends[key],
                int(kwargs.get("context_chars", 160)), hybrid_patterns,
            )
            row["evidence_span"] = {
                "start": chunk_starts[key],
                "end": chunk_ends[key],
                "excerpt": row["snippet"],
            }
            row["matched_terms"] = _matched_hybrid_terms(
                page_text, raw_queries, chunk_starts[key], chunk_ends[key],
            )
            row["evidence_type"] = evidence_type(
                page_text, chunk_starts[key], chunk_ends[key],
            )
            row["whole_word"] = True
            row["normalization_level"] = "broad_discovery"
            row["footnotes_excluded"] = True
            if row["book_id"] == "b14":
                row.update(_structural_identity(
                    page_text, chunk_starts[key], chunk_ends[key],
                    row.get("qasida_number"), row.get("qasida_bayt_count"),
                ))
        fused.append(row)
    for rank, row in enumerate(fused, start=offset + 1):
        row["rank"] = rank
    return fused


_REFORMULATION_STOPWORDS = ARABIC_STOPWORDS | {
    "هل", "كيف", "ماذا", "متي", "متى", "اين", "أين", "لماذا",
    "عليه", "عليها", "عليهم", "له", "لها", "لهم",
}


def controlled_reformulations(
    raw_queries: list[str], *, max_queries: int = 6,
) -> list[str]:
    """Reduce long natural-language questions to bounded evidence phrases.

    This is a deterministic fallback, not free-form query rewriting.  It keeps
    source-surface tokens, emits adjacent two-word topic phrases first, then a
    few individual content terms, and exposes every generated query to the
    caller.  Short evidence queries are left alone.
    """
    from app.services.question_intent import discovery_phrases
    return discovery_phrases(raw_queries, max_queries)


@profiled("reformulation_total")
def reformulated_search(**kwargs) -> list[dict]:
    """Retrieve compositional anchors in one FTS query, verify locally, then rank.

    Fixed candidate pools and source-local locators make pagination stable.
    Literal searches/counts retain their separate, exhaustive contracts.
    """
    from app.services.question_intent import plan, concept_patterns, concept_regex, assess_window, POLICY
    from app.core.evidence_blocks import block_at, INCLUDE_TOC
    raw_queries=kwargs.get('queries') or [kwargs.get('query')]
    raw_queries=[q for q in raw_queries if q]
    plans=[plan(q) for q in raw_queries]
    if not plans:return []
    forms=list(dict.fromkeys(form for p in plans for g in p['groups'] for form,_ in concept_patterns(g)))
    if not forms:forms=list(dict.fromkeys(t for p in plans for t in p['terms']))
    if not forms:return []
    # FTS does not encode source semantics; it supplies candidates only.
    expressions=[]
    for p in plans:
        if p['required']:
            expressions.append(' AND '.join('('+_fts_expression([form for form,_ in concept_patterns(g)],'OR','exact_phrase')+')' for g in p['required']))
    expression=(' OR '.join('('+e+')' for e in expressions)) if expressions else _fts_expression(forms,'OR','exact_phrase')
    scope={k:kwargs.get(k) for k in ('book_ids','source_code','page_from','page_to','qasida_number','min_tier')}
    filters,params=_search_filters(**scope)
    candidates=_connection().execute('SELECT p.book_id,p.seq,p.text,p.block_type,bm25(pages_fts) AS relevance FROM pages_fts JOIN pages p ON p.id=pages_fts.rowid JOIN books b ON b.book_id=p.book_id WHERE pages_fts MATCH ?'+filters+' ORDER BY relevance,p.book_id,p.seq LIMIT 160',[expression,*params]).fetchall()
    patterns=[(form,_pattern_for_query(form,'exact_phrase')) for form in forms]
    records=[]
    for candidate in candidates:
        from app.core.budget import expired
        if expired():break
        if candidate['block_type']=='toc' and not INCLUDE_TOC.get():continue
        source=_indexable_text(candidate['text'])
        evidence=[]
        # Anchor at every required primary concept, rather than at ubiquitous
        # supplementary words such as "work" or "time".
        primary=list(dict.fromkeys(g for p in plans for g in p['required'][:1]))
        anchors=[(g,concept_regex(g)) for g in primary] if primary else patterns
        seen=set(); window_cells=set()
        for form,pattern in anchors:
            for m in pattern.finditer(source):
                if m.start() in seen:continue
                seen.add(m.start())
                para_start,para_end=_complete_paragraph_window(source,m.start(),m.end())
                cell=(para_start,para_end) if para_end-para_start<=840 else (para_start,(m.start()-para_start)//120)
                if cell in window_cells:continue
                window_cells.add(cell)
                assessments=[assess_window(q,source,m.start(),m.end(),_build_exact_variant_regex) for q in raw_queries]
                valid=[a for a in assessments if a]
                if not valid or (kwargs.get('operator')=='AND' and len(valid)!=len(raw_queries)):continue
                intent=max(valid,key=lambda a:a['intent_score'])
                if not kwargs.get('include_topic_only',False) and intent['question_relevance']=='topic_only':continue
                evidence.append((intent,m.start(),m.end(),m.group()))
        if not evidence:continue
        intent,start,end,form=max(evidence,key=lambda x:(x[0]['intent_score'],-x[1]))
        page=get_page(candidate['book_id'],candidate['seq'])
        row={k:v for k,v in page.items() if k not in ('text','has_next','has_prev','content_types','evidence_blocks')}
        pattern=_pattern_for_query(form,'exact_phrase')
        row.update(intent)
        row.update(score=round(.93*intent['intent_score']+.07*_bounded_bm25(-candidate['relevance']),6),
            lexical_score=_bounded_bm25(-candidate['relevance']),match_type='reformulated',
            score_kind='local_intent_bm25_discovery',reformulated_query=form,
            original_queries=raw_queries,reformulation_method=POLICY,
            reformulation_warning='Discovery only; local concept co-occurrence does not verify an answer.',
            snippet=_evidence_excerpt(source,start,end,kwargs.get('context_chars',160),[pattern]),
            match_id=f"{page['book_id']}-p{page['seq']}-c{start}",
            matched_terms=_matched_literal_terms(source,[form],start,end),
            evidence_type=evidence_type(candidate['text'],start,start+1),
            evidence_type_method='heuristic',evidence_type_confidence='unverified',evidence_type_scope='start_anchor',
            block_type=block_at(candidate['text'],start,page['block_type']))
        row['evidence_span']={'start':start,'end':end,'excerpt':row['snippet']}
        if page['book_id']=='b14':row.update(_structural_identity(source,start,end,page.get('qasida_number'),page.get('qasida_bayt_count')))
        records.append(row)
    ranking=kwargs.get('ranking','relevance')
    if ranking in {'book_order','chronological'}:records.sort(key=lambda r:(r['book_id'],r['seq']))
    elif ranking=='primary_first':records.sort(key=primary_first_sort_key)
    else:records.sort(key=lambda r:(-r['score'],r['source_tier'],r['book_id'],r['seq']))
    records=[r for r in records if r['score']>=float(kwargs.get('min_score') or 0)]
    if kwargs.get('diversify_books',True) and len(kwargs.get('book_ids') or [])!=1:
        counts={};selected=[]
        for row in records:
            key=row['book_id']
            if counts.get(key,0)>=kwargs.get('max_per_book',2):continue
            counts[key]=counts.get(key,0)+1;selected.append(row)
        records=selected
    offset=max(0,int(kwargs.get('offset',0)));limit=max(1,int(kwargs.get('limit',10)))
    records=records[offset:offset+limit]
    for rank,row in enumerate(records,offset+1):row['rank']=rank
    return records


def _paragraph_window(text: str, match_start: int, match_end: int, context_chars: int) -> tuple[int, int]:
    """Prefer complete paragraph boundaries while enforcing a bounded window."""
    hard_start = max(0, match_start - context_chars)
    hard_end = min(len(text), match_end + context_chars)
    para_start = text.rfind("\n\n", hard_start, match_start)
    para_end = text.find("\n\n", match_end, hard_end)
    start = para_start + 2 if para_start >= 0 else hard_start
    end = para_end if para_end >= 0 else hard_end
    return start, end


def _complete_paragraph_window(text: str, match_start: int, match_end: int) -> tuple[int, int]:
    """Return the complete source paragraph containing an evidence span."""
    para_start = text.rfind("\n\n", 0, match_start)
    para_end = text.find("\n\n", match_end)
    return (para_start + 2 if para_start >= 0 else 0, para_end if para_end >= 0 else len(text))


def _cap_context_window(
    text: str, start: int, end: int, match_start: int, match_end: int,
    max_chars: int,
) -> tuple[int, int, bool]:
    """Cap an oversized context while keeping the evidence inside it."""
    if end - start <= max_chars:
        return start, end, False
    centre = (match_start + match_end) // 2
    capped_start = max(start, centre - max_chars // 2)
    capped_end = min(end, capped_start + max_chars)
    capped_start = max(start, capped_end - max_chars)
    return capped_start, capped_end, True


def _cross_page_paragraph(page, match_start, match_end, max_chars, max_pages=12):
    """Join source paragraphs across adjacent prose pages, with honest caps.

    Blank lines are the declared source boundary policy. A TOC or structured
    Diwan boundary is never guessed to be a prose continuation.
    """
    original = _indexable_text(page["text"])
    left, right = _complete_paragraph_window(original, match_start, match_end)
    segments = [(page, left, right, original[left:right])]
    left_done = left > 0 or page["seq"] == 1
    right_done = right < len(original)
    stop_reason = None
    for direction in (-1, 1):
        done = left_done if direction == -1 else right_done
        while not done:
            if len(segments) >= max_pages or sum(len(x[3]) for x in segments) >= max_chars:
                stop_reason = "page_or_character_cap"
                break
            edge = segments[0][0] if direction == -1 else segments[-1][0]
            adjacent = get_page(page["book_id"], edge["seq"] + direction)
            if adjacent is None:
                done = True
                break
            if (page.get("qasida_number") is not None or adjacent.get("qasida_number") is not None
                    or page.get("block_type") == "toc" or adjacent.get("block_type") == "toc"):
                stop_reason = "structural_boundary"
                break
            text = _indexable_text(adjacent["text"])
            boundary = text.rfind("\n\n") if direction == -1 else text.find("\n\n")
            a, b = ((boundary + 2 if boundary >= 0 else 0), len(text)) if direction == -1 else (0, boundary if boundary >= 0 else len(text))
            segment = (adjacent, a, b, text[a:b])
            if direction == -1:
                segments.insert(0, segment)
            else:
                segments.append(segment)
            done = boundary >= 0
        if direction == -1:
            left_done = done
        else:
            right_done = done
    joined = "\n".join(segment[3] for segment in segments)
    evidence_offset = 0
    for source, a, b, text in segments:
        if source["seq"] == page["seq"]:
            evidence_offset += match_start - a
            break
        evidence_offset += len(text) + 1
    a, b, capped = _cap_context_window(joined, 0, len(joined), evidence_offset,
                                      evidence_offset + max(1, match_end-match_start), max_chars)
    citations = []
    cursor = 0
    for source, start, end, text in segments:
        lo, hi = max(a, cursor), min(b, cursor + len(text))
        if hi > lo:
            citations.append({"book_id": source["book_id"], "seq": source["seq"],
                "printed_page": source.get("printed_page"), "citation_label": source["citation_label"],
                "source_start": start + lo - cursor, "source_end": start + hi - cursor,
                "passage_start": lo - a, "passage_end": hi - a})
        cursor += len(text) + 1
    complete = left_done and right_done and not capped
    continuation = []
    if not complete and (capped or stop_reason == "page_or_character_cap") and citations:
        for direction, segment in (("before", citations[0]), ("after", citations[-1])):
            source = get_page(page["book_id"], segment["seq"])
            if source is None:
                continue
            seq = segment["seq"]
            position = segment["source_start"]-1 if direction == "before" else segment["source_end"]
            if position < 0 or position >= len(_indexable_text(source["text"])):
                seq += -1 if direction == "before" else 1
                source = get_page(page["book_id"], seq)
                if source is None:
                    continue
                position = max(0,len(_indexable_text(source["text"]))-1) if direction == "before" else 0
            continuation.append({"direction":direction,
                "match_id":f"{page['book_id']}-p{seq}-c{position}",
                "context_mode":"paragraph", "note":"Context continuation locator, not a new query match."})
    return {"passage": joined[a:b], "context_segments": citations,
        "continuation": continuation,
        "complete_paragraph": complete,
        "context_scope": "complete_paragraph" if complete else "partial_paragraph",
        "context_boundary_policy": "source_blank_lines_across_adjacent_prose_pages",
        "context_cap_applied": capped or stop_reason == "page_or_character_cap",
        "context_stop_reason": stop_reason if not complete else None,
        "context_max_chars": max_chars, "context_max_pages": max_pages,
        "cross_page": len(citations) > 1, "truncated": not complete,
        "original_match": {"book_id": page["book_id"], "seq": page["seq"],
            "start": match_start, "end": match_end},
        "passage_evidence_span": {"start": evidence_offset-a,
                                  "end": min(b-a, evidence_offset-a+max(1,match_end-match_start))}}


_MATCH_ID_RE = re.compile(r"^(b\d+)-p(\d+)-c(\d+)$")


def get_passage(
    book_id: str, seq: int, query: str | None = None, context_chars: int = 800,
    match_start: int | None = None, context_mode: str = "bounded",
    max_chars: int = 12000,
) -> dict | None:
    """Return bounded context or an explicitly complete source paragraph."""
    if context_mode not in {"bounded", "paragraph"}:
        raise ValueError("context_mode must be bounded or paragraph")
    requested_max_chars = int(max_chars)
    max_chars = max(1, min(int(max_chars), 20000))
    page = get_page(book_id, seq)
    if page is None:
        return None
    pattern = _build_highlight_regex(query.strip()) if query else None
    text = page["text"]
    if match_start is not None and not 0 <= match_start < len(text):
        return None
    match = (pattern.match(text, match_start) if match_start is not None else pattern.search(text)) if pattern else None
    complete_paragraph = False
    context_cap_applied = False
    if match is None and match_start is not None:
        match_start = max(0, min(match_start, len(text)))
        match_end = min(len(text), match_start + 1)
        if context_mode == "paragraph":
            start, end = _complete_paragraph_window(text, match_start, match_end)
            start, end, context_cap_applied = _cap_context_window(
                text, start, end, match_start, match_end, max_chars,
            )
            complete_paragraph = not context_cap_applied
        else:
            start, end = _paragraph_window(text, match_start, match_end, context_chars)
        passage = ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")
        occurrences = None
    elif match:
        if context_mode == "paragraph":
            start, end = _complete_paragraph_window(text, match.start(), match.end())
            start, end, context_cap_applied = _cap_context_window(
                text, start, end, match.start(), match.end(), max_chars,
            )
            complete_paragraph = not context_cap_applied
        else:
            start, end = _paragraph_window(text, match.start(), match.end(), context_chars)
        passage = text[start:end]
        prefix, suffix = ("…" if start else ""), ("…" if end < len(text) else "")
        passage, occurrences = _highlight(passage, pattern)
        passage = prefix + passage + suffix
    else:
        start, end = 0, min(len(text), context_chars * 2)
        passage = text[start:end]
        occurrences = 0
    identity = _structural_identity(
        text,
        match.start() if match else int(match_start or 0),
        match.end() if match else int(match_start or 0) + 1,
        page.get("qasida_number"), page.get("qasida_bayt_count"),
    )
    result = {key: value for key, value in {
        "book_id": page["book_id"], "book_title": page["book_title"],
        "tier": page["source_tier"], "seq": page["seq"],
        "source_author": page.get("source_author"),
        "compiler": page.get("compiler"),
        "authorship_mode": page.get("authorship_mode"),
        "attribution_confidence": page.get("attribution_confidence"),
        "provenance_status": page.get("provenance_status"),
        "canonical_book_id": page.get("canonical_book_id"),
        "edition_relation": page.get("edition_relation"),
        "searchable_by_default": bool(page.get("searchable_by_default")),
        "printed_page": page["printed_page"], "citation_label": page["citation_label"],
        "qasida_number": page.get("qasida_number"), "qasida_title": page.get("qasida_title"),
        "qasida_bayt_count": page.get("qasida_bayt_count"),
        "bayt_from": page.get("bayt_from"), "bayt_to": page.get("bayt_to"),
        "page_bayt_from": page.get("bayt_from"),
        "page_bayt_to": page.get("bayt_to"),
        "bayt_range_scope": "page" if page.get("bayt_from") is not None else None,
        "occurrences": occurrences,
        "passage": passage, "page_chars": len(text),
        "truncated": start > 0 or end < len(text),
        "context_scope": (
            "complete_paragraph" if complete_paragraph else "bounded_excerpt"
        ),
        "complete_paragraph": complete_paragraph,
        "context_cap_applied": context_cap_applied,
        "content_types": page.get("content_types"),
        "evidence_type": evidence_type(
            text,
            match.start() if match else int(match_start or 0),
            match.end() if match else int(match_start or 0) + 1,
        ),
    }.items() if value is not None}
    result.update(identity)
    from app.core.evidence_blocks import block_at
    anchor = match.start() if match else int(match_start or 0)
    result.update(citation_metadata(book_id, seq, page["printed_page"]))
    result.update(block_type=block_at(text, anchor, page["block_type"]),
                  evidence_type=evidence_type(text, anchor, anchor+1),
                  evidence_type_method="heuristic", evidence_type_confidence="unverified",
                  evidence_type_scope="start_anchor", requested_max_chars=requested_max_chars,
                  effective_max_chars=max_chars)
    if context_mode == "paragraph":
        original_start = match.start() if match else int(match_start or 0)
        original_end = match.end() if match else original_start + 1
        result.update(_cross_page_paragraph(page, original_start, original_end, max_chars))
        result["context_offsets_basis"] = "unhighlighted_passage"
        result["original_match_scope"] = "query_span" if match else "start_anchor"
        if pattern:
            result["passage"], result["occurrences"] = _highlight(result["passage"], pattern)
    return result


def get_passage_by_match_id(
    match_id: str, context_chars: int = 800, context_mode: str = "bounded",
    max_chars: int = 12000,
) -> dict | None:
    match = _MATCH_ID_RE.fullmatch(match_id or "")
    if not match:
        return None
    book_id, seq, start = match.group(1), int(match.group(2)), int(match.group(3))
    return get_passage(
        book_id, seq, context_chars=context_chars, match_start=start,
        context_mode=context_mode, max_chars=max_chars,
    )


def get_bayt(
    stable_id: str, context_chars: int = 800, context_mode: str = "bounded",
    max_chars: int = 12000,
) -> dict | None:
    """Resolve one canonical Dīwān stable ID with page context."""
    row = _connection().execute(
        "SELECT stable_id, book_id, qasida_number, bayt_number, page_id, "
        "start_char, end_char, text FROM bayts WHERE stable_id=?",
        (stable_id,),
    ).fetchone()
    if not row:
        heading = re.fullmatch(r"b14-q(\d{3})-h", stable_id or "")
        if not heading:
            return None
        page_row = _connection().execute("SELECT seq,text FROM pages WHERE book_id='b14' AND qasida_number=? ORDER BY seq LIMIT 1", (int(heading.group(1)),)).fetchone()
        if not page_row:
            return None
        result = get_passage('b14', page_row['seq'], match_start=0,
                             context_chars=context_chars, context_mode=context_mode,max_chars=max_chars)
        result.update(stable_id=stable_id, stable_id_kind='qasida_heading',heading_id=stable_id)
        result.pop('bayt_number',None)
        return result
    page = _connection().execute(
        "SELECT seq FROM pages WHERE id=?", (row["page_id"],),
    ).fetchone()
    result = get_passage(
        row["book_id"], int(page["seq"]), context_chars=context_chars,
        match_start=int(row["start_char"]), context_mode=context_mode,
        max_chars=max_chars,
    ) or {}
    result.update({
        "stable_id": row["stable_id"],
        "stable_id_kind": "bayt",
        "qasida_number": int(row["qasida_number"]),
        "bayt_number": int(row["bayt_number"]),
        "bayt_text": clean_structured_bayt_text(row["text"]),
    })
    return result


def get_qasida(qasida_number: int) -> dict | None:
    """Return a complete qaṣīda and its full page/citation map in one call."""
    conn = _connection()
    rows = conn.execute(
        """SELECT y.stable_id, y.bayt_number, y.text, p.seq, p.printed_page,
                  p.citation_label, p.qasida_title, p.qasida_bayt_count
           FROM bayts y JOIN pages p ON p.id=y.page_id
           WHERE y.book_id='b14' AND y.qasida_number=?
           ORDER BY y.bayt_number""",
        (int(qasida_number),),
    ).fetchall()
    if not rows:
        return None
    pages: list[dict] = []
    seen_pages: set[int] = set()
    bayts = []
    for row in rows:
        bayts.append({
            "stable_id": row["stable_id"],
            "bayt_number": int(row["bayt_number"]),
            "text": clean_structured_bayt_text(row["text"]),
            "seq": int(row["seq"]),
            "printed_page": row["printed_page"],
        })
        if int(row["seq"]) not in seen_pages:
            pages.append({
                "seq": int(row["seq"]),
                "printed_page": row["printed_page"],
                "citation_label": row["citation_label"],
            })
            seen_pages.add(int(row["seq"]))
    declared = int(rows[0]["qasida_bayt_count"] or len(rows))
    return {
        "container_id": f"b14-q{int(qasida_number):03d}",
        "book_id": "b14",
        "qasida_number": int(qasida_number),
        "qasida_title": _concise_qasida_title(rows[0]["qasida_title"]),
        "qasida_bayt_count": declared,
        "returned_bayts": len(bayts),
        "complete": len(bayts) == declared,
        "pages": pages,
        "bayts": bayts,
        "prosody": {
            "status": "not_curated",
            "bahr": None,
            "qafiya": None,
            "rawi": None,
            "warning": "No prosodic value is claimed until scholarly review.",
        },
    }


def get_parallel_candidates(stable_id: str, limit: int = 5) -> list[dict]:
    """Expose the built Dīwān parallel index without claiming verification."""
    rows = _connection().execute(
        """SELECT d.candidate_stable_id, d.shared_roots, d.shared_root_count,
                  d.rarity_score, d.evidence_kind, d.review_status,
                  d.citation_safe, d.index_version, y.qasida_number,
                  y.bayt_number, y.text
           FROM diwan_parallel_candidates d
           JOIN bayts y ON y.stable_id=d.candidate_stable_id
           WHERE d.source_stable_id=?
           ORDER BY d.rarity_score DESC, d.candidate_stable_id LIMIT ?""",
        (stable_id, max(1, min(int(limit), 20))),
    ).fetchall()
    return [dict(row) | {"citation_safe": bool(row["citation_safe"])} for row in rows]


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


def zero_result_diagnostics(
    queries, *, attempted_modes, book_ids=None, source_code=None, page_from=None,
    page_to=None, qasida_number=None, min_tier=None, whole_word=True,
    min_score=0.0, offset=0, include_topic_only=False, operator="OR",
):
    """Only offer a retry after verifying it with the same source scope."""
    from app.services.question_intent import content_terms
    terms=list(dict.fromkeys(t for q in queries for t in content_terms(q)))
    scope=dict(book_ids=book_ids,source_code=source_code,page_from=page_from,
               page_to=page_to,qasida_number=qasida_number,min_tier=min_tier)
    per_term=[]
    if 'reformulated' not in attempted_modes:
        for term in terms[:8]:
            stats=search_stats([term],whole_word=whole_word,**scope)
            per_term.append(dict(term=term,matching_pages=stats['matching_pages'],occurrences=stats['matching_occurrences']))
    else:
        for term in terms[:16]:
            row=_connection().execute("SELECT documents FROM term_document_frequency WHERE term=?",(normalize_search_text(term,level='broad'),)).fetchone()
            per_term.append({'term':term,'matching_pages':row[0] if row else 0,'frequency_scope':'whole_corpus_precomputed_not_scoped_census'})
    retry=None;stage='matching_or_scope'
    base=dict(queries=queries,operator=operator,whole_word=whole_word,limit=1,
              diversify_books=False,**scope)
    fn=reformulated_search if 'reformulated' in attempted_modes else (hybrid_search if 'hybrid' in attempted_modes else search)
    mode=attempted_modes[-1]
    if fn==search:base['search_mode']={'exact':'exact_phrase','terms':'all_words','lexeme':'lexeme'}.get(mode,'exact_phrase')
    if offset:
        if fn(**base,min_score=min_score):
            stage='pagination';retry={'offset':0,'match_mode':'auto' if mode=='reformulated' else mode}
    if retry is None and min_score>0 and fn(**base,min_score=0):
        stage='score_filter';retry={'offset':0,'min_score':0,'match_mode':'auto' if mode=='reformulated' else mode}
    if retry is None:
        from itertools import combinations
        for pair in list(combinations(terms,2))[:12]:
            phrase=' '.join(pair);candidates=search(query=phrase,search_mode='all_words',limit=4,ranking='primary_first',**scope)
            if candidates:
                retry={'query':phrase,'match_mode':'terms','offset':0,'min_score':0}
                if any(r['source_tier']<=3 for r in candidates):break
    if retry is None and mode=='reformulated' and not include_topic_only and reformulated_search(**base,include_topic_only=True):
        stage='relation_filter';retry={'match_mode':'auto','include_topic_only':True,'offset':0,'min_score':0}
    # A safe exact single-term recovery is useful exploration, explicitly not
    # an answer. Its count already proves a match under this navigation scope.
    if retry is None:
        available=[x for x in per_term if x['matching_pages']]
        if available:
            term=min(available,key=lambda x:x['matching_pages'])['term']
            if search(query=term,search_mode='exact_phrase',limit=1,**scope):
                retry={'query':term,'match_mode':'exact','offset':0,'min_score':0}
    retry_tiers=[]
    if retry and retry.get('query'):
        checked=search(query=retry['query'],search_mode='all_words' if retry['match_mode']=='terms' else 'exact_phrase',limit=4,ranking='primary_first',**scope)
        retry_tiers=sorted({r['source_tier'] for r in checked})
    if retry:
        from app.core.evidence_blocks import INCLUDE_TOC
        if 'query' not in retry:retry['queries']=queries
        retry['operator']=operator
        retry['include_toc']=INCLUDE_TOC.get()
    return {'zero_result_is_not_absence_proof':True,'empty_stage':stage,
            'attempted_modes':attempted_modes,'per_term':per_term,
            'dropped_stopwords':[t for q in queries for t in safe_tokens(q) if t not in terms],
            'suggested_mode':retry.get('match_mode') if retry else None,
            'verified_retry':dict(retry,**{k:v for k,v in scope.items() if v is not None},whole_word=whole_word) if retry else None,
            'retry_source_tiers':retry_tiers,
            'retry_warning':'Only tier 4/5 evidence was found by this checked retry.' if retry_tiers and min(retry_tiers)>=4 else None,
            'retry_scope':'exploration_not_verified_answer',
            'message':'No displayed evidence met the request; do not infer corpus absence. A verified_retry, when present, was checked in the same source scope.'}
