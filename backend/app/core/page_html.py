"""
Render the blocks from text_format.py as HTML.

The server-rendered pages and the React app now agree on both halves of the
job: text_format.py / formatText.js recover the same structure, and this
module / PageText.jsx dress it the same way. The markup and the class names
are deliberately identical, so the CSS in html_templates.py and the CSS in
frontend/src/index.css stay readable side by side.
"""
from __future__ import annotations

import re
from html import escape as _esc

from app.core.text_format import segment_page

DIACRITIC = re.compile(r"[\u064B-\u0652\u0670]")
LETTER = re.compile(r"[\u0621-\u063A\u0641-\u064A]")

# `(نص الآية)` optionally followed by `48 الروم` — 2,615 of these in the corpus.
BRACKETED = re.compile(r"\(([^()]{8,400})\)(\s*\d{1,3}\s+[\u0621-\u064A]{3,})?")
# `"متن الحديث"` — 3,541 in the corpus.
QUOTED = re.compile(r"[\"“]([^\"“”]{8,400})[\"”]")

TAG_SPLIT = re.compile(r"(<[^>]+>)")


def _vowel_ratio(s: str) -> float:
    letters = len(LETTER.findall(s))
    if not letters:
        return 0.0
    return len(DIACRITIC.findall(s)) / letters


def _escape_text(s: str) -> str:
    """Escape for element content. Quotation marks are left alone — they are
    how the source marks a quoted hadith, and escaping them first would hide
    that from the decorator below."""
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def decorate_inline(text: str) -> str:
    """Escape `text`, then mark up the quotations inside it.

    A bracketed passage counts as Qur'an when it is voweled the way the mushaf
    is and runs to more than a couple of words; anything shorter is an aside
    from the author and is left alone.
    """
    html = _escape_text(text)
    html = QUOTED.sub(lambda m: f'<span class="q-hadith">{m.group(1)}</span>', html)

    def _ayah(m: re.Match) -> str:
        inner, ref = m.group(1), m.group(2)
        if len(inner.split()) < 3 or _vowel_ratio(inner) < 0.3:
            return m.group(0)
        cite = f'<span class="q-ref">{ref.strip()}</span>' if ref else ""
        return f'<span class="q-ayah">{inner.strip()}</span>{cite}'

    return BRACKETED.sub(_ayah, html)


def highlight_html(html: str, pattern: re.Pattern | None) -> str:
    """Apply `pattern` to the text of an HTML string, never inside a tag, so
    the decoration added above survives untouched."""
    if pattern is None:
        return html
    parts = TAG_SPLIT.split(html)
    return "".join(
        p if p.startswith("<") else pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", p)
        for p in parts
    )


def render_inline(text: str, pattern: re.Pattern | None = None) -> str:
    return highlight_html(decorate_inline(text), pattern)


def _bayt_html(b: dict, pattern) -> str:
    single = not b["sadr"] or not b["ajuz"]
    meta = ""
    if b.get("number") or b.get("ref"):
        meta = (
            '<span class="bayt__meta">'
            f'<span class="bayt__num">{_esc(b.get("number") or "")}</span>'
            f'<span class="bayt__ref">{_esc(b.get("ref") or "")}</span>'
            "</span>"
        )
    if single:
        body = render_inline(b["sadr"] or b["ajuz"], pattern)
        return f'<div class="blk bayt bayt--single"><span class="bayt__sadr">{body}</span>{meta}</div>'
    return (
        '<div class="blk bayt">'
        f'<span class="bayt__sadr">{render_inline(b["sadr"], pattern)}</span>'
        '<span class="bayt__rosette">۞</span>'
        f'<span class="bayt__ajuz">{render_inline(b["ajuz"], pattern)}</span>'
        f"{meta}</div>"
    )


def blocks_to_html(blocks: list[dict], pattern: re.Pattern | None = None) -> str:
    out = []
    for b in blocks:
        t = b["type"]
        if t == "bayt":
            out.append(_bayt_html(b, pattern))
        elif t == "heading":
            out.append(f'<h3 class="blk blk-heading">{render_inline(b["text"], pattern)}</h3>')
        elif t == "quote":
            out.append(f'<p class="blk blk-quote">{render_inline(b["text"], pattern)}</p>')
        elif t == "folio":
            out.append(f'<p class="blk blk-folio">{_esc(b["text"])}</p>')
        elif t == "divider":
            out.append('<div class="blk blk-divider" role="separator"></div>')
        else:
            out.append(f'<p class="blk blk-para">{render_inline(b["text"], pattern)}</p>')
    return "\n".join(out)


def page_to_html(text: str, pattern: re.Pattern | None = None) -> str:
    """Segment a stored page and render it as a formatted text block."""
    blocks = segment_page(text)
    if not blocks:
        return '<p class="blk blk-para empty">هذه الصفحة خالية من النص</p>'
    return blocks_to_html(blocks, pattern)
