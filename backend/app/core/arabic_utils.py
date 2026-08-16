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
ARABIC_STOPWORDS = frozenset({"في", "على", "من", "الى", "عن", "ما", "ان", "الذي"})

# Conservative concept aliases used by proximity/terms retrieval.  These are
# lexical families, not a claim of semantic equivalence; they only generate
# candidates which are still ranked by chunk-local co-occurrence.
_LEXICAL_FAMILIES = {
    "المحافظه": ("حافظ", "حفظ", "المحافظه"),
    "محافظه": ("حافظ", "حفظ", "محافظه"),
    "الصلاه": ("الصلاه", "صلاه"),
    "وقتها": ("وقتها", "وقت"),
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


def normalized_tokens(text: str, *, drop_stopwords: bool = False) -> list[str]:
    """Return canonical Arabic tokens for every retrieval subsystem."""
    words = normalize_arabic(text, aggressive=True).split()
    return [w for w in words if not drop_stopwords or w not in ARABIC_STOPWORDS]


def lexical_variants(token: str) -> tuple[str, ...]:
    """Small, deterministic lexical expansion for proximity retrieval."""
    token = normalize_arabic(token, aggressive=True)
    variants = {token}
    if token.startswith("ال") and len(token) > 4:
        variants.add(token[2:])
    elif len(token) >= 3:
        variants.add("ال" + token)
    variants.update(_LEXICAL_FAMILIES.get(token, ()))
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
