"""
Parsers for each supported format.
Each parser returns a list of PageContent objects with page_number and text.
"""
from __future__ import annotations
import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PageContent:
    page_number: int              # sequential, 1-based — used for navigation (prev/next)
    text: str
    page_label: str | None = None  # real Shamela-style label, e.g. "1/205" (vol/page)
    volume: int | None = None      # volume number parsed from the marker, if any


# ── PDF ───────────────────────────────────────────────────────────────────────
def parse_pdf(path: Path) -> list[PageContent]:
    try:
        import pdfplumber
        pages: list[PageContent] = []
        with pdfplumber.open(str(path)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
                if text.strip():
                    pages.append(PageContent(page_number=i, text=text))
        return pages
    except Exception as exc:
        logger.error("PDF parse error %s: %s", path, exc)
        return []


# ── DOCX ──────────────────────────────────────────────────────────────────────
def parse_docx(path: Path) -> list[PageContent]:
    """
    DOCX has no hard page boundaries, so we approximate pages by grouping
    every N paragraphs (≈ 30) into a logical 'page'.  Users can still navigate
    to the right section, even if numbering differs slightly from Word's.
    """
    import docx
    PARA_PER_PAGE = 30
    try:
        doc = docx.Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    except Exception as exc:
        logger.error("DOCX parse error %s: %s", path, exc)
        return []

    pages: list[PageContent] = []
    for page_idx in range(0, len(paragraphs), PARA_PER_PAGE):
        chunk = paragraphs[page_idx: page_idx + PARA_PER_PAGE]
        pages.append(PageContent(
            page_number=page_idx // PARA_PER_PAGE + 1,
            text="\n".join(chunk),
        ))
    return pages


# ── HTML ──────────────────────────────────────────────────────────────────────
def parse_html(path: Path) -> list[PageContent]:
    from bs4 import BeautifulSoup
    import chardet

    try:
        raw = path.read_bytes()
        enc = chardet.detect(raw).get("encoding") or "utf-8"
        soup = BeautifulSoup(raw.decode(enc, errors="replace"), "lxml")
    except Exception as exc:
        logger.error("HTML parse error %s: %s", path, exc)
        return []

    # Remove script / style noise
    for tag in soup(["script", "style", "head"]):
        tag.decompose()

    # Try to honour explicit page-break divs/spans, else treat whole doc as p.1
    page_breaks = soup.find_all(
        lambda t: t.name in {"div", "section", "article"}
        and any("page" in (t.get("class") or []) or "chapter" in (t.get("class") or []) for _ in [None])
    )

    if page_breaks:
        pages = [PageContent(i + 1, pb.get_text(" ", strip=True))
                 for i, pb in enumerate(page_breaks)]
    else:
        # Treat whole document as a single page; chunking happens later
        text = soup.get_text(" ", strip=True)
        pages = [PageContent(1, text)]

    return [p for p in pages if p.text.strip()]


# ── TXT (Shamela-style exports) ─────────────────────────────────────────────
# Shamela .txt exports mark the END of every real page with a standalone line
# that looks like "(1/1)", "(1/2)", ... "(1/205)"  →  (volume / page).
# The number after the slash is the actual printed page number; the number
# before it is the volume. We split on these markers instead of guessing a
# fixed character window, so the page shown to the user matches the real book.
_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

_PAGE_MARKER_RE = re.compile(
    r"^[ \t]*\(\s*([0-9\u0660-\u0669]+)\s*/\s*([0-9\u0660-\u0669]+)\s*\)[ \t]*$",
    re.MULTILINE,
)


def _to_int(digits: str) -> int:
    return int(digits.translate(_INDIC_DIGITS))


def _decode_txt(raw: bytes) -> str:
    import chardet
    detected = chardet.detect(raw)
    enc = detected.get("encoding") or "utf-8"
    confidence = detected.get("confidence") or 0
    # chardet is very reliable on windows-1256 (cp1256) for these exports,
    # but fall back sensibly if confidence is low or decoding fails.
    candidates = [enc] if confidence >= 0.5 else []
    candidates += ["windows-1256", "utf-8-sig", "utf-8"]
    for candidate in candidates:
        try:
            decoded = raw.decode(candidate)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        decoded = raw.decode(enc, errors="replace")
    # Shamela exports are typically CRLF/CR — normalise so the marker regex
    # (anchored with ^/$) matches every marker line reliably.
    return decoded.replace("\r\n", "\n").replace("\r", "\n")


def _parse_txt_fixed_window(text: str) -> list[PageContent]:
    """Fallback for .txt files that don't contain Shamela page markers."""
    CHARS_PER_PAGE = 3000
    pages: list[PageContent] = []
    for i in range(0, len(text), CHARS_PER_PAGE):
        chunk = text[i: i + CHARS_PER_PAGE].strip()
        if chunk:
            n = i // CHARS_PER_PAGE + 1
            pages.append(PageContent(page_number=n, text=chunk, page_label=str(n)))
    return pages


def parse_txt(path: Path) -> list[PageContent]:
    raw = path.read_bytes()
    text = _decode_txt(raw)

    matches = list(_PAGE_MARKER_RE.finditer(text))
    if not matches:
        logger.info("No (vol/page) markers found in %s — using fixed-window chunking", path)
        return _parse_txt_fixed_window(text)

    pages: list[PageContent] = []
    cursor = 0
    for m in matches:
        segment = text[cursor:m.start()].strip()
        cursor = m.end()
        if not segment:
            continue
        vol = _to_int(m.group(1))
        pg = _to_int(m.group(2))
        pages.append(PageContent(
            page_number=len(pages) + 1,
            text=segment,
            page_label=f"{vol}/{pg}",
            volume=vol,
        ))

    # Anything left after the final marker (rare — usually just trailing
    # whitespace) is appended as one last page so no content is dropped.
    tail = text[cursor:].strip()
    if tail:
        last_vol = pages[-1].volume if pages else 1
        pages.append(PageContent(
            page_number=len(pages) + 1,
            text=tail,
            page_label=f"{last_vol}/تتمة",
            volume=last_vol,
        ))

    return pages


# ── Dispatcher ────────────────────────────────────────────────────────────────
_PARSERS = {
    ".pdf":  parse_pdf,
    ".docx": parse_docx,
    ".doc":  parse_docx,   # python-docx handles older .doc only if converted; warn below
    ".html": parse_html,
    ".htm":  parse_html,
    ".txt":  parse_txt,
}


def parse_document(path: Path) -> list[PageContent]:
    ext = path.suffix.lower()
    parser = _PARSERS.get(ext)
    if parser is None:
        logger.warning("No parser for %s — skipping", path)
        return []
    return parser(path)
