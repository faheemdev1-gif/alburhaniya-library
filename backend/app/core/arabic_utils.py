"""
Arabic text normalisation helpers.
Strips tashkeel (diacritics), normalises Alef / Ya / Waw variants,
and removes tatweel (kashida) so index lookups are consistent.
"""
import re
import unicodedata


# ── character maps ────────────────────────────────────────────────────────────
_ALEF_VARIANTS   = "\u0622\u0623\u0625\u0671"   # آأإٱ  → ا
_YA_VARIANTS     = "\u0649\u06cc\u06d2"             # ى ی ے → ي
_TA_MARBUTA      = "\u0629"                       # ة  → ه
_KAF_VARIANTS    = "\u06a9\u06aa"                 # ک ڪ → ك
_TATWEEL         = "\u0640"                       # ـ  kashida

_DIACRITICS = re.compile(
    "[\u064b-\u065f"   # fathatan … wavy hamza below
    "\u0610-\u061a"    # Arabic extended
    "\u06d6-\u06dc"    # Quran-specific marks
    "\u06df-\u06e4"
    "\u06e7\u06e8"
    "\u06ea-\u06ed\u0670]"
)

_PUNCT_WS = re.compile(r"[\u060c\u061b\u061f،؛؟!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~\s]+")

# Function words never contribute to lexical relevance.  Keep this in the
# canonical text module so terms, hybrid ranking and future indexers cannot
# silently acquire different lists.
ARABIC_STOPWORDS = frozenset({"في", "علي", "من", "الي", "عن", "ما", "ان", "الذي"})

# Concept retrieval may ignore explicit nominal negation while retaining the
# meaningful verb/noun that follows it.  Strict terms retrieval never uses
# this set and therefore remains literal.
HYBRID_STOPWORDS = ARABIC_STOPWORDS | frozenset({"عدم"})

# Conservative concept aliases used by hybrid/proximity retrieval.  These are
# lexical families, not a claim of semantic equivalence; they only generate
# candidates which are still ranked by chunk-local co-occurrence.
_LEXICAL_FAMILIES = {
    "المحافظه": ("حافظ", "حافظوا", "حفظ", "يحافظ", "يحافظون", "المحافظه"),
    "محافظه": ("حافظ", "حافظوا", "حفظ", "يحافظ", "يحافظون", "محافظه"),
    "حفظ": ("حافظ", "حافظوا", "حفظ", "يحافظ", "يحافظون", "محافظه", "المحافظه"),
    "الصلاه": ("الصلاه", "صلاه", "صلوات", "صلواته", "الصلوات"),
    "صلاه": ("الصلاه", "صلاه", "صلوات", "صلواته", "الصلوات"),
    "وقتها": ("وقتها", "وقت", "اوقات", "اوقاتها"),
    "الوقتها": ("وقتها", "وقت", "اوقات", "اوقاتها"),
    "تاخيرها": ("تاخير", "تاخيرها", "يؤخر", "يوخر", "اخر"),
}

_LEXICAL_ROOTS = {
    "المحافظه": "حفظ",
    "محافظه": "حفظ",
    "حفظ": "حفظ",
}


def strip_diacritics(text: str) -> str:
    return _DIACRITICS.sub("", text)


def normalize_alef(text: str) -> str:
    for ch in _ALEF_VARIANTS:
        text = text.replace(ch, "\u0627")
    return text


def normalize_ya(text: str) -> str:
    for ch in _YA_VARIANTS:
        text = text.replace(ch, "\u064a")
    return text


def normalize_kaf(text: str) -> str:
    for ch in _KAF_VARIANTS:
        text = text.replace(ch, "\u0643")
    return text


def normalize_ta_marbuta(text: str) -> str:
    return text.replace(_TA_MARBUTA, "\u0647")


def remove_tatweel(text: str) -> str:
    return text.replace(_TATWEEL, "")


def normalize_arabic(text: str, *, aggressive: bool = False) -> str:
    """
    Standard pipeline used for both indexing and query-time normalisation.
    `aggressive=True` also normalises ة → ه (useful for search queries).
    """
    text = strip_diacritics(text)
    text = remove_tatweel(text)
    text = normalize_alef(text)
    text = normalize_ya(text)
    text = normalize_kaf(text)
    # Search-only canonical expansion of the common honorific ligature.
    text = text.replace("ﷺ", "صلى الله عليه وسلم")
    # Treat punctuation as a word boundary so phrases still match when the
    # source inserts commas, Quranic brackets, or editorial punctuation.
    text = _PUNCT_WS.sub(" ", text)
    if aggressive:
        text = normalize_ta_marbuta(text)
    # collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_search_text(text: str, *, level: str = "safe") -> str:
    """Normalize Arabic under an explicit, research-safe policy.

    ``surface`` removes only tashkil/tatweel and normalizes whitespace.
    ``safe`` additionally normalizes Unicode Kaf variants, but deliberately
    preserves hamzated Alef, Alef Maqsura/Ya, and Ta Marbuta/Ha.  Those
    distinctions can change the word and must not inflate literal censuses.
    ``broad`` is recall-oriented and applies the legacy aggressive mapping; it
    is suitable only for lexeme/hybrid candidate discovery and must never be
    reported as literal evidence.
    """
    if level not in {"surface", "safe", "broad"}:
        raise ValueError("normalization level must be surface, safe, or broad")
    value = strip_diacritics(remove_tatweel(text or ""))
    value = value.replace("ﷺ", "صلى الله عليه وسلم")
    if level in {"safe", "broad"}:
        value = normalize_kaf(value)
    if level == "broad":
        value = normalize_ta_marbuta(normalize_ya(normalize_alef(value)))
    value = _PUNCT_WS.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip()


def safe_tokens(text: str, *, drop_stopwords: bool = False) -> list[str]:
    """Return citation-safe tokens without collapsing distinct Arabic forms."""
    words = normalize_search_text(text, level="safe").split()
    if not drop_stopwords:
        return words
    # Stopwords are stored in the legacy broad form. Compare only for dropping;
    # never replace the authoritative safe token returned to the caller.
    return [
        word for word in words
        if normalize_search_text(word, level="broad") not in ARABIC_STOPWORDS
    ]


def safe_term_variants(token: str) -> tuple[str, ...]:
    """Article-only variants for literal exact/terms retrieval."""
    token = normalize_search_text(token, level="safe")
    variants = {token}
    if token.startswith("ال") and len(token) > 4:
        variants.add(token[2:])
    elif len(token) >= 3:
        variants.add("ال" + token)
    return tuple(sorted(value for value in variants if value))


def normalized_tokens(text: str, *, drop_stopwords: bool = False) -> list[str]:
    """Return canonical Arabic tokens for every retrieval subsystem."""
    words = normalize_arabic(text, aggressive=True).split()
    return [w for w in words if not drop_stopwords or w not in ARABIC_STOPWORDS]


def hybrid_tokens(text: str) -> list[str]:
    """Content tokens for conceptual retrieval, with common clitics removed."""
    tokens: list[str] = []
    for word in normalized_tokens(text):
        base = (
            word[1:]
            if word not in _LEXICAL_FAMILIES and word[:1] in {"و", "ف"} and len(word) > 3
            else word
        )
        if base and base not in HYBRID_STOPWORDS:
            tokens.append(base)
    return tokens


def lexical_variants(token: str) -> tuple[str, ...]:
    """Concept-oriented variants for hybrid/proximity retrieval only.

    This deliberately includes a few derivational relatives.  Callers that
    promise literal term presence must use :func:`term_variants` instead.
    """
    token = normalize_arabic(token, aggressive=True)
    variants = set(term_variants(token))
    variants.update(_LEXICAL_FAMILIES.get(token, ()))
    return tuple(sorted(variants))


def lexical_root(token: str) -> str | None:
    """Return a declared root for curated lexeme families, when available."""
    return _LEXICAL_ROOTS.get(normalize_arabic(token, aggressive=True))


def term_variants(token: str) -> tuple[str, ...]:
    """Strict variants for ``terms`` retrieval.

    Only the normalized token and its definite/indefinite article form are
    allowed.  Root, derivational, synonym and concept expansion belongs to
    lexeme or hybrid retrieval and must never leak into ``terms`` results.
    """
    token = normalize_arabic(token, aggressive=True)
    variants = {token}
    if token.startswith("ال") and len(token) > 4:
        variants.add(token[2:])
    elif len(token) >= 3:
        variants.add("ال" + token)
    return tuple(sorted(variants))


def split_into_chunks(text: str, chunk_size: int = 400, overlap: int = 80) -> list[str]:
    """
    Split Arabic text into overlapping chunks by word boundary.
    Returns a list of chunk strings.
    """
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = start
        length = 0
        while end < len(words) and length + len(words[end]) + 1 <= chunk_size:
            length += len(words[end]) + 1
            end += 1
        if end == start:          # single word longer than chunk_size
            end = start + 1
        chunks.append(" ".join(words[start:end]))
        # step forward, keeping overlap words
        overlap_words = max(0, end - start - overlap // 6)  # rough word estimate
        start += overlap_words if overlap_words > 0 else 1

    return chunks
