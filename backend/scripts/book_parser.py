"""
Parses shamela.ws-exported .htm books (windows-1256 encoded) into clean
plain-text pages. Same parsing logic used for the static-site export —
kept here too so the backend's search index and the static site always
agree on page numbering and text.
"""
from __future__ import annotations
import re
from bs4 import BeautifulSoup

ANCHOR = "</div></ul></td></tr></table><ul><p>"
PAGE_MARK_RE = re.compile(
    r"<Font color=['\"]Blue['\"]><I><p align=['\"]left['\"]>"
    r"\(\s*(\d*)\s*/\s*(\d*)\s*\)</p></I></font>\s*<hr[^>]*>",
    re.IGNORECASE,
)


def clean_fragment_to_paragraphs(html_fragment: str) -> list[str]:
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
