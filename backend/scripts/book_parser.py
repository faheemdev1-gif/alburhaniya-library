"""
Parses shamela.ws-exported .htm books (windows-1256 encoded) into clean
plain-text pages. Same parsing logic used for the static-site export —
kept here too so the backend's search index and the static site always
agree on page numbering and text.

Also handles books that can't be represented in windows-1256 at all
(e.g. sources using the U+FDFA sallallahu-alayhi-wasallam ligature,
Quranic ornate brackets ﴿ ﴾, Arabic-Indic digits, or other modern
Unicode outside that legacy codepage) via parse_utf8_pages(), which
reads a pre-segmented UTF-8 JSON file instead of a shamela .htm export.
Both functions return the same shape: a list of
{"printed_page": str|None, "paragraphs": [str, ...]} dicts, one per page,
so build_index.py doesn't need to care which path a given book came from.
"""
from __future__ import annotations
import json
import re

ANCHOR = "</div></ul></td></tr></table><ul><p>"
PAGE_MARK_RE = re.compile(
    r"<Font color=['\"]Blue['\"]><I><p align=['\"]left['\"]>"
    r"\(\s*(\d*)\s*/\s*(\d*)\s*\)</p></I></font>\s*<hr[^>]*>",
    re.IGNORECASE,
)


def clean_fragment_to_paragraphs(html_fragment: str) -> list[str]:
    # Import lazily so structure-only parser tests can run without loading the
    # optional HTML stack. Production builds still install beautifulsoup4/lxml.
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_fragment, "lxml")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text()

    paragraphs, buf = [], []
    for line in text.split("\n"):
        line = line.strip()
        if line:
            buf.append(line)
        elif buf:
            paragraphs.append(" ".join(buf).strip())
            buf = []
    if buf:
        paragraphs.append(" ".join(buf).strip())

    cleaned = []
    for p in paragraphs:
        if re.fullmatch(r"[-_ـ=\s]{3,}", p):
            continue
        if p:
            cleaned.append(p)
    return cleaned


def parse_book(raw_path: str) -> list[dict]:
    """Returns a list of {printed_page, paragraphs} dicts, one per source page."""
    data = open(raw_path, "rb").read()
    text = data.decode("windows-1256", errors="replace")

    idx = text.find(ANCHOR)
    if idx == -1:
        raise ValueError(f"content-start anchor not found in {raw_path}")
    content = text[idx + len(ANCHOR):]

    pages = []
    prev_end = 0
    for m in PAGE_MARK_RE.finditer(content):
        printed_page = m.group(2) or None
        fragment = content[prev_end:m.start()]
        paragraphs = clean_fragment_to_paragraphs(fragment)
        if paragraphs:
            pages.append({"printed_page": printed_page, "paragraphs": paragraphs})
        prev_end = m.end()

    return pages



def split_oversized_pages(
    pages: list[dict], *, max_words: int = 1600, min_words: int = 700
) -> list[dict]:
    """Split pathological source pages into bounded, paragraph-safe segments.

    Normal books retain their original pagination. A page is split only when
    it exceeds ``max_words``; paragraph boundaries are preserved whenever
    possible, and unusually large paragraphs are split by sentence.
    """
    sentence_re = re.compile(r"(?<=[.!؟؛:])\s+")
    output = []
    for page in pages:
        paragraphs = list(page.get("paragraphs") or [])
        if sum(len(x.split()) for x in paragraphs) <= max_words:
            output.append(page)
            continue

        units = []
        for paragraph in paragraphs:
            if len(paragraph.split()) <= max_words:
                units.append(paragraph)
                continue
            parts = sentence_re.split(paragraph)
            buf, count = [], 0
            for part in parts:
                n = len(part.split())
                if buf and count + n > max_words:
                    units.append(" ".join(buf).strip())
                    buf, count = [], 0
                buf.append(part); count += n
            if buf:
                units.append(" ".join(buf).strip())

        chunks, buf, count = [], [], 0
        for unit in units:
            n = len(unit.split())
            if buf and count + n > max_words and count >= min_words:
                chunks.append(buf); buf, count = [], 0
            buf.append(unit); count += n
        if buf:
            chunks.append(buf)

        for chunk_index, chunk in enumerate(chunks, start=1):
            label = page.get("page_label")
            if label and len(chunks) > 1:
                label = f"{label} — مقطع {chunk_index}"
            output.append({
                "printed_page": page.get("printed_page"),
                "page_label": label,
                "paragraphs": chunk,
            })
    return output

def parse_utf8_pages(raw_path: str) -> list[dict]:
    """
    Load a pre-segmented UTF-8 book: a JSON file containing a flat list of
    {"printed_page": str|None, "paragraphs": [str, ...]} dicts — the exact
    same shape parse_book() returns for shamela .htm exports.

    Use this for books whose source text can't be represented in
    windows-1256 (e.g. contains the U+FDFA sallallahu-alayhi-wasallam
    ligature, Quranic ornate brackets ﴿ ﴾, Arabic-Indic digits, or other
    modern Unicode not in that legacy codepage). Nothing here re-encodes
    or substitutes characters — full source fidelity is the point.
    """
    with open(raw_path, encoding="utf-8") as f:
        pages = json.load(f)

    if not isinstance(pages, list):
        raise ValueError(f"{raw_path}: expected a JSON list of page dicts")
    for i, page in enumerate(pages):
        if "paragraphs" not in page:
            raise ValueError(f"{raw_path}: page {i} missing 'paragraphs'")
        page.setdefault("printed_page", None)
        page.setdefault("page_label", None)

    return pages
