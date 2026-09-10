"""
Structure recovery for library pages.

The shamela exports flatten every page into running text. Poetry survives only
as a `***` between the two hemistichs of a bayt, and consecutive bayts — often
with commentary running straight into them — sit on one line:

    …قال رضي الله عنه: صدر *** عجز (240 ق 2) ثم قال: صدر *** عجز…

Finding where the verse starts and stops is the whole problem. The reliable
signal is vocalisation: in this corpus poetry is fully voweled (median
diacritic-to-letter ratio 0.75) while the surrounding commentary is bare
(median 0.00). So we classify each word, grow a verse span outward from every
`***`, and stop where the vowels stop. Inside a span the `***` marks exact
hemistich boundaries; where two bayts run together with nothing between them,
we cut on the bayt number if there is one and otherwise on metre — hemistichs
within a qasida are near-constant in length.

This is the Python twin of frontend/src/utils/formatText.js and is kept
deliberately in lockstep with it: both are verified to emit identical blocks
across all 7,450 pages. Change one, change the other.

Blocks returned by segment_page():
    {"type": "bayt",    "number": str|None, "ref": str|None,
     "sadr": str, "ajuz": str}
    {"type": "para",    "text": str}
    {"type": "heading", "text": str}
    {"type": "quote",   "text": str}
    {"type": "divider"}
    {"type": "folio",   "text": str}
"""
from __future__ import annotations

import re

# ── character classes ───────────────────────────────────────────────────────
DIACRITIC = re.compile(r"[\u064B-\u0652\u0670]")
LETTER = re.compile(r"[\u0621-\u063A\u0641-\u064A]")

# Exactly three asterisks separate the two hemistichs of a bayt (8,849 of them
# in the corpus). Four or more is a decorative section rule.
SEP_TOKEN = "***"
SEP_RE = re.compile(r"(?<!\*)\*{3}(?!\*)")
RULE_RE = re.compile(r"^(?:\*{4,}|\*{2,}[-–—_]{2,}[\s\S]*)$")
RULE_SPLIT = re.compile(r"(\*{2,}[-–—_]{3,}\*{3}[-–—_]{3,}\*{2,}|\*{4,})")

# `419-` and `3 ق 1:` (bayt 3 of qasida 1) both head a bayt.
_QAF = r"\d{1,4}\s*(?:-\s*\d{1,4}\s*)?ق\s*\d{1,3}"
LEAD_QAF = re.compile(r"^(" + _QAF + r")\s*:\s*")
LEAD_NUM = re.compile(r"^(\d{1,4})\s*[-‑–ـ]\s*")
BAYT_MARK = re.compile(r"(?:(" + _QAF + r")\s*:|(\d{1,4})\s*[-‑–ـ])\s*")

# A bayt's own citation, e.g. `(240 ق 2)` or `(13 - 15 ق 57)`.
TRAILING_REF = re.compile(r"\s*\(\s*" + _QAF + r"\s*\)\s*$")
ANY_REF = re.compile(r"^\(\s*" + _QAF + r"\s*\)$")
LEADING_REF = re.compile(r"^\(\s*" + _QAF + r"\s*\)\s*")
LONE_MARKER = re.compile(r"^(?:(" + _QAF + r")\s*:|(\d{1,4})\s*[-‑–ـ])$")

# `-33-` on its own: the printed folio number left over from the scan.
FOLIO_RE = re.compile(r"^[-‑–—]\s*(\d{1,4})\s*[-‑–—]$")

# Source scans sometimes glue the printed folio and a decorative rule to the
# final bayt on a page.  Those marks belong to page metadata / layout, not to
# the canonical verse text stored in ``bayts``.  Keep this helper deliberately
# narrow so ordinary punctuation inside a bayt is never rewritten.
STRUCTURED_FOLIO_TRAILER_RE = re.compile(
    r"\s*(?:\[\s*[0-9٠-٩۰-۹]{1,4}\s*\]|[-‑–—]\s*[0-9٠-٩۰-۹]{1,4}\s*[-‑–—])\s*$"
)
STRUCTURED_RULE_TRAILER_RE = re.compile(
    r"\s*(?:\*{2,}[-–—_]{3,}\*{3,}[-–—_]{3,}\*{2,}|\*{4,})\s*$"
)

# Median hemistich in this corpus is 43 characters (n=1,270, σ≈8).
DEFAULT_HEMISTICH = 43
# A word this voweled is almost certainly verse (or a quoted verse of Qur'an).
VOCALISED = 0.35

_WS = re.compile(r"\s+")
_INVERTED_QURAN_BRACKETS = re.compile(
    r"\]\s*((?=[^\[\]\n]{6,800}\s*\[)[^\[\]\n]*[\u0621-\u06ff][^\[\]\n]*?)\s*\["
)

VERSE, NEUTRAL, PROSE = 1, 0, -1


def repair_quran_display_brackets(text: str) -> tuple[str, bool]:
    """Repair bidi-inverted Qur'an brackets for display, never stored text."""
    repaired, count = _INVERTED_QURAN_BRACKETS.subn(
        lambda match: f"﴿ {match.group(1).strip()} ﴾", text or "",
    )
    return repaired, bool(count)


def clean_structured_bayt_text(text: str) -> str:
    """Remove scan-only material from a canonical bayt copy.

    Raw page text remains untouched and therefore keeps its diplomatic source
    representation.  This function is only for structured bayt records and is
    idempotent so it can also protect responses built from an older database.
    """
    value = (text or "").rstrip()
    value = STRUCTURED_FOLIO_TRAILER_RE.sub("", value).rstrip()
    value = STRUCTURED_RULE_TRAILER_RE.sub("", value).rstrip()
    # A rule may itself have been followed by the folio marker.
    value = STRUCTURED_FOLIO_TRAILER_RE.sub("", value).rstrip()
    return value


def _clean(s: str) -> str:
    return _WS.sub(" ", s or "").strip()


def _strip_edges(s: str) -> str:
    s = _clean(s)
    s = re.sub(r"^[\s*\-–—_=~،,.:؛]+", "", s)
    s = re.sub(r"[\s*\-–—_=~،,؛]+$", "", s)
    return s


def _vowel_ratio(word: str) -> float:
    letters = len(LETTER.findall(word))
    if not letters:
        return 0.0
    return len(DIACRITIC.findall(word)) / letters


def _classify(word: str) -> int:
    """Verse-like, prose-like, or neutral.

    Short function words (‎و، في، من، لا) carry no vowels either way, so they
    stay neutral and inherit the run around them instead of breaking it.
    """
    letters = len(LETTER.findall(word))
    if letters == 0 or letters <= 2:
        return NEUTRAL
    return VERSE if _vowel_ratio(word) >= VOCALISED else PROSE


def _boundary_flags(words: list[str]) -> list[bool]:
    """Hard stops a verse span may never run through.

    `:` is an attribution — `قال رضي الله عنه:` — and the verse begins after
    it. Quotes mark hadith. Brackets need care: poets quote a single Qur'anic
    word inside a bayt — `وَمَاتَ الْخَوْفُ عَنَّا حَيْثُ (إِنَّا)` — and
    treating that as a stop would swallow the hemistich. So a bracketed group
    only counts when it is a real aside: two or more words, or a `ق` citation.
    """
    flags = [w != SEP_TOKEN and bool(re.search(r"[:：\"“”«»]", w)) for w in words]

    open_at = -1
    for i, w in enumerate(words):
        if w == SEP_TOKEN:
            continue
        if open_at < 0 and "(" in w:
            open_at = i
        if open_at >= 0 and ")" in w:
            group = words[open_at : i + 1]
            if len(group) >= 2 or re.search(r"ق\s*\d", " ".join(group)):
                for j in range(open_at, i + 1):
                    flags[j] = True
            open_at = -1
    if open_at >= 0:
        flags[open_at] = True
    return flags


def _verse_spans(words: list[str]) -> list[list[int]]:
    """Maximal, merged spans of verse around each `***`, as [start, end) pairs."""
    kinds = [VERSE if w == SEP_TOKEN else _classify(w) for w in words]
    bounds = _boundary_flags(words)
    spans: list[list[int]] = []

    for i, word in enumerate(words):
        if word != SEP_TOKEN:
            continue
        if spans and spans[-1][1] > i:
            continue

        # Walk out both ways, tolerating a single neutral word but stopping at
        # two prose words in a row, or at any hard boundary.
        start = i
        prose = 0
        for j in range(i - 1, -1, -1):
            if bounds[j]:
                break
            if kinds[j] == PROSE:
                prose += 1
                if prose >= 2:
                    break
            elif kinds[j] == VERSE:
                prose = 0
            start = j
        while start < i and kinds[start] != VERSE and words[start] != SEP_TOKEN:
            start += 1

        end = i + 1
        prose = 0
        for j in range(i + 1, len(words)):
            if bounds[j]:
                break
            if kinds[j] == PROSE:
                prose += 1
                if prose >= 2:
                    break
            elif kinds[j] == VERSE:
                prose = 0
            end = j + 1
        while end > i + 1 and kinds[end - 1] != VERSE and words[end - 1] != SEP_TOKEN:
            end -= 1

        if spans and start <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], end)
        else:
            spans.append([start, end])
    return spans


def _split_near_length(text: str, target: float) -> tuple[str, str]:
    """Split at the word boundary whose left side lands closest to `target`."""
    s = _clean(text)
    if not s:
        return "", ""
    best, best_cost = -1, float("inf")
    for m in re.finditer(r"\s+", s):
        cost = abs(m.start() - target)
        if cost < best_cost:
            best_cost, best = cost, m.start()
    if best < 0:
        return s, ""
    return s[:best].strip(), s[best:].strip()


def _split_middle(chunk: str, target: float) -> tuple[str, str, str | None]:
    """A chunk between two `***` holds the ajuz of one bayt then the sadr of
    the next. A bayt number is exact, so it wins; otherwise use metre."""
    s = _clean(chunk)
    for m in BAYT_MARK.finditer(s):
        if m.start() == 0:  # belongs to the previous bayt's numbering
            continue
        left = s[: m.start()].strip()
        right = s[m.end() :].strip()
        if left and right:
            return left, right, _clean(m.group(1) or m.group(2) or "")
        break
    left, right = _split_near_length(s, target)
    return left, right, None


def _take_leading_number(text: str) -> tuple[str | None, str]:
    s = _clean(text)
    m = LEAD_QAF.match(s)
    if m:
        return _clean(m.group(1)), s[m.end() :].strip()
    m = LEAD_NUM.match(s)
    if m:
        return m.group(1), s[m.end() :].strip()
    return None, s


def _take_trailing_ref(text: str) -> tuple[str | None, str]:
    s = _clean(text)
    m = TRAILING_REF.search(s)
    if not m:
        return None, s
    ref = _clean(m.group(0).strip().strip("()"))
    return ref, s[: m.start()].strip()


def _span_to_bayts(span_text: str) -> list[dict]:
    chunks = [c.strip() for c in _clean(span_text).split(SEP_TOKEN)]
    k = len(chunks) - 1
    if k < 1:
        return []

    middles = [c for c in chunks[1:-1] if c]
    target = (
        sum(len(c) for c in middles) / len(middles) / 2 if middles else DEFAULT_HEMISTICH
    )

    halves = [chunks[0]]
    markers: list[str | None] = [None] * k
    for i in range(1, k):
        left, right, marker = _split_middle(chunks[i], target)
        halves.extend([left, right])
        if marker:
            markers[i] = marker
    halves.append(chunks[k])

    bayts = []
    for i in range(k):
        sadr = halves[i * 2] if i * 2 < len(halves) else ""
        ajuz = halves[i * 2 + 1] if i * 2 + 1 < len(halves) else ""
        number = markers[i]

        lead_num, rest = _take_leading_number(sadr)
        if lead_num:
            number = number or lead_num
            sadr = rest
        ref, ajuz = _take_trailing_ref(ajuz)

        sadr = _strip_edges(sadr)
        ajuz = _strip_edges(ajuz)
        if not sadr and not ajuz:
            continue
        bayts.append(
            {
                "type": "bayt",
                "number": number or None,
                "ref": ref or None,
                "sadr": sadr,
                "ajuz": ajuz,
            }
        )
    return bayts


# ── prose ───────────────────────────────────────────────────────────────────

LEAD_LABEL = re.compile(
    r"^(المعنى|المعني|الشرح|شرح المفردات|المفردات|اللغة|الإعراب|المناسبة"
    r"|ملحوظة|ملاحظة|فائدة|تنبيه)\s*:\s*"
)
STANDALONE_QUOTE = re.compile(r"^[\"“«]([\s\S]{8,})[\"”»]$")
HEADING_START = re.compile(r"^(باب|فصل|مقدمة|خاتمة|تمهيد|القصيدة|قصيدة|الوصية|خطاب|وصية)(?=\s|$)")


def _is_heading(s: str) -> bool:
    if len(s) > 70:
        return False
    if re.search(r"[.؟!]$", s):
        return False
    if HEADING_START.match(s):
        return True
    # A trailing colon only makes a heading out of a short, comma-free label —
    # otherwise it is just a sentence introducing what comes next.
    if s.endswith(":") and len(s) <= 50 and not re.search(r"[,،؛]", s):
        return True
    return False


def _prose_blocks(text: str) -> list[dict]:
    raw = _clean(text)
    if not raw:
        return []

    # Match the folio and a lone bayt marker first: _strip_edges would eat the
    # dashes and colons that identify them.
    m = FOLIO_RE.match(raw)
    if m:
        return [{"type": "folio", "text": m.group(1)}]
    if RULE_RE.match(raw):
        return [{"type": "divider"}]
    m = LONE_MARKER.match(raw)
    if m:
        return [{"type": "marker", "text": _clean(m.group(1) or m.group(2))}]

    s = _strip_edges(raw)
    if not s:
        return []
    if ANY_REF.match(s):
        return []  # `(240 ق 2)` — already carried on its bayt

    s = LEADING_REF.sub("", s).strip()
    if not s:
        return []

    q = STANDALONE_QUOTE.match(s)
    if q and not re.search(r"[\"“«]", q.group(1)):
        return [{"type": "quote", "text": q.group(1).strip()}]

    # `المعني: …` opens the commentary. Peel the label off first so a short
    # gloss is not mistaken for a heading in its entirety.
    label = LEAD_LABEL.match(s)
    if label:
        rest = s[label.end() :].strip()
        if not rest:
            return [{"type": "heading", "text": label.group(1)}]
        return [
            {"type": "heading", "text": label.group(1)},
            {"type": "para", "text": rest},
        ]

    if _is_heading(s):
        return [{"type": "heading", "text": s}]
    return [{"type": "para", "text": s}]


# ── entry point ─────────────────────────────────────────────────────────────


def _segment_paragraph(paragraph: str, out: list[dict]) -> None:
    if SEP_TOKEN not in paragraph:
        out.extend(_prose_blocks(paragraph))
        return

    words = [w for w in paragraph.split(" ") if w]
    spans = _verse_spans(words)
    if not spans:
        out.extend(_prose_blocks(" ".join(paragraph.split(SEP_TOKEN))))
        return

    cursor = 0
    for start, end in spans:
        if start > cursor:
            out.extend(_prose_blocks(" ".join(words[cursor:start])))
        bayts = _span_to_bayts(" ".join(words[start:end]))
        if bayts:
            out.extend(bayts)
        else:
            out.extend(_prose_blocks(" ".join(" ".join(words[start:end]).split(SEP_TOKEN))))
        cursor = end
    if cursor < len(words):
        out.extend(_prose_blocks(" ".join(words[cursor:])))


def segment_page(raw: str) -> list[dict]:
    """Turn a page's stored text into typed blocks."""
    if not raw:
        return []
    blocks: list[dict] = []

    for raw_paragraph in re.split(r"\n{2,}", str(raw)):
        paragraph = _clean(raw_paragraph)
        if not paragraph:
            continue

        # Peel off decorative rules FIRST — they are often glued to real text
        # (`… **----***----** -33-`) and contain a `***` of their own, which
        # would otherwise be mistaken for a hemistich separator.
        for part in RULE_SPLIT.split(paragraph):
            piece = _clean(part)
            if not piece:
                continue
            if re.match(r"^(?:\*{4,}|\*{2,}[-–—_])", piece):
                if blocks and blocks[-1]["type"] != "divider":
                    blocks.append({"type": "divider"})
                continue
            _segment_paragraph(SEP_RE.sub(" " + SEP_TOKEN + " ", piece), blocks)

    # A marker that arrived on its own line numbers the bayt that follows it.
    folded: list[dict] = []
    for i, b in enumerate(blocks):
        if b["type"] != "marker":
            folded.append(b)
            continue
        nxt = blocks[i + 1] if i + 1 < len(blocks) else None
        if nxt and nxt["type"] == "bayt":
            nxt["number"] = nxt["number"] or b["text"]
        else:
            folded.append({"type": "heading", "text": b["text"]})

    while folded and folded[0]["type"] == "divider":
        folded.pop(0)
    while folded and folded[-1]["type"] == "divider":
        folded.pop()
    return folded


def to_plain_text(blocks: list[dict]) -> str:
    """Flatten blocks back to plain text, but with the structure visible.

    For MCP and any other text-only consumer: a bayt gets its own line with a
    rosette between the hemistichs, so a model can see where each verse ends
    instead of guessing at a `***` run. Costs almost nothing in tokens versus
    the flattened original.
    """
    lines: list[str] = []
    for b in blocks:
        t = b["type"]
        if t == "bayt":
            num = f'{b["number"]}- ' if b.get("number") else ""
            ref = f'  ({b["ref"]})' if b.get("ref") else ""
            if b["sadr"] and b["ajuz"]:
                lines.append(f'{num}{b["sadr"]}  ۞  {b["ajuz"]}{ref}')
            else:
                lines.append(f'{num}{b["sadr"] or b["ajuz"]}{ref}')
        elif t == "divider":
            lines.append("* * *")
        elif t == "folio":
            lines.append(f'[{b["text"]}]')
        elif t == "heading":
            lines.append("")
            lines.append(b["text"])
        else:
            lines.append(b["text"])
    return "\n".join(lines).strip()


def format_page(raw: str) -> str:
    """Convenience: stored page text -> structure-preserving plain text."""
    return to_plain_text(segment_page(raw))
