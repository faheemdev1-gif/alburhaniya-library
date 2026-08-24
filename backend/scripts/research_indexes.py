"""Build conservative token evidence and Dīwān-parallel candidate indexes.

The root column is deliberately nullable.  It is populated only from the
audited families below; no guessed triliteral root is ever presented as fact.
Parallel rows are discovery candidates and are explicitly unsafe for citation
until a scholar reviews the underlying abyāt.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import defaultdict
from itertools import combinations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.arabic_utils import normalize_arabic  # noqa: E402


ARABIC_TOKEN_RE = re.compile(r"[\u0621-\u06ff]+")
ANALYSIS_VERSION = "curated-arabic-roots-v1"
PARALLEL_VERSION = "diwan-shared-rare-roots-v1"

# root -> (lemma, explicitly audited normalized forms)
_CURATED_FAMILIES: dict[str, tuple[str, set[str]]] = {
    "حفظ": ("حفظ", {"حفظ", "حافظ", "محافظ", "محافظه"}),
    "غني": ("غني", {"غني", "غني", "غناء", "اغتني", "استغني", "مغني"}),
    "فقر": ("فقر", {"فقر", "فقير", "فقراء", "افتقر", "افتقار", "مفتقر"}),
    "وصل": ("وصل", {"وصل", "وصال", "واصل", "موصول"}),
    "فني": ("فني", {"فني", "فناء", "فان"}),
    "بقي": ("بقي", {"بقي", "بقاء", "باق"}),
    "حمد": ("حمد", {"حمد", "احمد", "محمد", "محمود"}),
    "علم": ("علم", {"علم", "عالم", "علوم", "معلوم", "معلم"}),
    "عرف": ("عرف", {"عرف", "معرفه", "عارف", "عرفان", "معروف"}),
    "ذكر": ("ذكر", {"ذكر", "ذاكر", "مذكور", "اذكار"}),
    "شهد": ("شهد", {"شهد", "شهود", "شاهد", "مشاهد"}),
    "حبب": ("حب", {"حب", "حبيب", "محبوب", "محبه"}),
    "نور": ("نور", {"نور", "انوار", "منير", "منوره"}),
    "روح": ("روح", {"روح", "ارواح", "روحاني"}),
    "قلب": ("قلب", {"قلب", "قلوب"}),
    "وحد": ("وحد", {"وحد", "واحد", "واحديه", "وحدانيه"}),
}

_PREFIXES = ("وال", "فال", "بال", "كال", "لل", "ال", "و", "ف", "ب", "ك", "ل")
_SUFFIXES = ("يات", "ات", "ون", "ين", "ان", "هما", "هم", "هن", "ها", "نا", "كم", "كن", "ه", "ي", "ك", "ا")


def _analysis_candidates(token_norm: str) -> set[str]:
    """Conservative affix candidates used only against the curated lexicon."""
    values = {token_norm}
    for prefix in _PREFIXES:
        if token_norm.startswith(prefix) and len(token_norm) - len(prefix) >= 3:
            values.add(token_norm[len(prefix):])
    for value in list(values):
        for suffix in _SUFFIXES:
            if value.endswith(suffix) and len(value) - len(suffix) >= 3:
                values.add(value[:-len(suffix)])
    return values


def curated_analysis(token_norm: str) -> tuple[str | None, str | None]:
    """Return (lemma, root) only when an audited family matches."""
    candidates = _analysis_candidates(token_norm)
    for root, (lemma, forms) in _CURATED_FAMILIES.items():
        if candidates & forms:
            return lemma, root
    return None, None


SCHEMA = """
CREATE TABLE IF NOT EXISTS tokens (
    token_id INTEGER PRIMARY KEY,
    page_id INTEGER NOT NULL,
    book_id TEXT NOT NULL,
    qasida_number INTEGER,
    bayt_number INTEGER,
    stable_id TEXT,
    position INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    surface_form TEXT NOT NULL,
    token_norm TEXT NOT NULL,
    lemma TEXT,
    root TEXT,
    analysis_version TEXT,
    FOREIGN KEY (page_id) REFERENCES pages(id),
    FOREIGN KEY (stable_id) REFERENCES bayts(stable_id)
);
CREATE INDEX IF NOT EXISTS idx_tokens_norm ON tokens(token_norm);
CREATE INDEX IF NOT EXISTS idx_tokens_root ON tokens(root) WHERE root IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tokens_bayt_position ON tokens(stable_id, position);
CREATE INDEX IF NOT EXISTS idx_tokens_page_position ON tokens(page_id, position);

CREATE TABLE IF NOT EXISTS diwan_parallel_candidates (
    source_stable_id TEXT NOT NULL,
    candidate_stable_id TEXT NOT NULL,
    shared_roots TEXT NOT NULL,
    shared_root_count INTEGER NOT NULL,
    rarity_score REAL NOT NULL,
    evidence_kind TEXT NOT NULL,
    review_status TEXT NOT NULL CHECK (review_status='unverified_candidate'),
    citation_safe INTEGER NOT NULL CHECK (citation_safe=0),
    index_version TEXT NOT NULL,
    PRIMARY KEY (source_stable_id, candidate_stable_id),
    FOREIGN KEY (source_stable_id) REFERENCES bayts(stable_id),
    FOREIGN KEY (candidate_stable_id) REFERENCES bayts(stable_id),
    CHECK (source_stable_id <> candidate_stable_id)
);
CREATE INDEX IF NOT EXISTS idx_parallel_source_score
ON diwan_parallel_candidates(source_stable_id, rarity_score DESC);
"""


def _stable_id_for_offset(ranges: list[sqlite3.Row], offset: int) -> tuple[str | None, int | None]:
    for row in ranges:
        if int(row["start_char"]) <= offset < int(row["end_char"]):
            return str(row["stable_id"]), int(row["bayt_number"])
    return None, None


def build_token_index(conn: sqlite3.Connection) -> dict[str, int]:
    conn.executescript(SCHEMA)
    conn.execute("DELETE FROM tokens")
    conn.row_factory = sqlite3.Row
    token_rows: list[tuple] = []
    total = rooted = 0
    pages = conn.execute(
        "SELECT id, book_id, qasida_number, text FROM pages ORDER BY id"
    ).fetchall()
    for page in pages:
        ranges = []
        if page["book_id"] == "b14":
            ranges = conn.execute(
                "SELECT stable_id, bayt_number, start_char, end_char FROM bayts "
                "WHERE page_id=? ORDER BY start_char", (page["id"],),
            ).fetchall()
        for position, match in enumerate(ARABIC_TOKEN_RE.finditer(page["text"])):
            surface = match.group(0)
            token_norm = normalize_arabic(surface, aggressive=True)
            if not token_norm:
                continue
            lemma, root = curated_analysis(token_norm)
            stable_id, bayt_number = _stable_id_for_offset(ranges, match.start())
            token_rows.append((
                page["id"], page["book_id"], page["qasida_number"], bayt_number,
                stable_id, position, match.start(), match.end(), surface, token_norm,
                lemma, root, ANALYSIS_VERSION if root else None,
            ))
            total += 1
            rooted += int(root is not None)
            if len(token_rows) >= 5000:
                conn.executemany(
                    "INSERT INTO tokens (page_id, book_id, qasida_number, bayt_number, "
                    "stable_id, position, char_start, char_end, surface_form, token_norm, "
                    "lemma, root, analysis_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    token_rows,
                )
                token_rows.clear()
    if token_rows:
        conn.executemany(
            "INSERT INTO tokens (page_id, book_id, qasida_number, bayt_number, "
            "stable_id, position, char_start, char_end, surface_form, token_norm, "
            "lemma, root, analysis_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            token_rows,
        )
    return {"tokens": total, "rooted_tokens": rooted}


def build_diwan_parallel_index(conn: sqlite3.Connection, per_bayt: int = 12) -> dict[str, int]:
    conn.execute("DELETE FROM diwan_parallel_candidates")
    roots_by_bayt: dict[str, set[str]] = defaultdict(set)
    for stable_id, root in conn.execute(
        "SELECT DISTINCT stable_id, root FROM tokens "
        "WHERE stable_id IS NOT NULL AND root IS NOT NULL"
    ):
        roots_by_bayt[str(stable_id)].add(str(root))
    bayts_by_root: dict[str, set[str]] = defaultdict(set)
    for stable_id, roots in roots_by_bayt.items():
        for root in roots:
            bayts_by_root[root].add(stable_id)
    total_bayts = int(conn.execute(
        "SELECT COUNT(*) FROM bayts WHERE book_id='b14'"
    ).fetchone()[0])
    max_df = max(3, int(total_bayts * 0.08))
    pair_roots: dict[tuple[str, str], set[str]] = defaultdict(set)
    for root, stable_ids in bayts_by_root.items():
        if not 2 <= len(stable_ids) <= max_df:
            continue
        for left, right in combinations(sorted(stable_ids), 2):
            pair_roots[(left, right)].add(root)
    ranked: dict[str, list[tuple[float, str, set[str]]]] = defaultdict(list)
    for (left, right), roots in pair_roots.items():
        score = sum(
            math.log((total_bayts + 1) / (len(bayts_by_root[root]) + 1))
            for root in roots
        )
        ranked[left].append((score, right, roots))
        ranked[right].append((score, left, roots))
    inserts: list[tuple] = []
    for source, candidates in ranked.items():
        candidates.sort(key=lambda item: (-item[0], -len(item[2]), item[1]))
        for score, candidate, roots in candidates[:per_bayt]:
            inserts.append((
                source, candidate,
                json.dumps(sorted(roots), ensure_ascii=False, separators=(",", ":")),
                len(roots), round(score, 6), "shared_rare_curated_roots",
                "unverified_candidate", 0, PARALLEL_VERSION,
            ))
    conn.executemany(
        "INSERT INTO diwan_parallel_candidates "
        "(source_stable_id, candidate_stable_id, shared_roots, shared_root_count, "
        "rarity_score, evidence_kind, review_status, citation_safe, index_version) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        inserts,
    )
    return {"parallel_candidates": len(inserts)}


def build_research_indexes(conn: sqlite3.Connection) -> dict[str, int]:
    token_stats = build_token_index(conn)
    parallel_stats = build_diwan_parallel_index(conn)
    return {**token_stats, **parallel_stats}
