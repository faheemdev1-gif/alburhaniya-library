"""
Drop-in replacement for however build_index.py currently opens each
book_*.htm file. Fixes the b14-style corruption (mojibake / "ï؟½..."),
which happens when a source file isn't actually UTF-8 (commonly legacy
Arabic Windows-1256) but gets read with encoding="utf-8" (or
errors="replace"), silently turning every non-ASCII byte into U+FFFD.

Usage in build_index.py:

    from safe_read import read_html_text

    # BEFORE (likely current code):
    # with open(path, encoding="utf-8") as f:
    #     html = f.read()

    # AFTER:
    html, used_encoding = read_html_text(path)
    if used_encoding != "utf-8":
        print(f"[warn] {path} was NOT utf-8, decoded as {used_encoding}")
"""
from __future__ import annotations

from pathlib import Path

from charset_normalizer import from_path

# Arabic legacy encodings to try, in priority order, before falling back
# to charset_normalizer's statistical guess. cp1256 is the extremely
# common "Windows Arabic" codepage used by a lot of older Arabic HTML.
_CANDIDATE_ENCODINGS = ["utf-8", "cp1256", "iso-8859-6", "windows-1252"]


def _looks_corrupted(text: str) -> bool:
    """Heuristic: real Arabic text should contain Arabic-block characters.
    Mojibake from this specific failure mode shows up as U+FFFD or the
    ï/؟/½ mojibake trio and basically no U+0600-06FF characters at all.
    """
    if not text:
        return True
    arabic_chars = sum(1 for ch in text if "\u0600" <= ch <= "\u06FF")
    replacement_chars = text.count("\ufffd")
    # If we see essentially no real Arabic and/or lots of replacement
    # chars relative to length, treat this decode attempt as bad.
    return arabic_chars < 5 or replacement_chars > len(text) * 0.05


def read_html_text(path: str | Path) -> tuple[str, str]:
    """Read an HTML/text file and return (text, encoding_used).

    Tries a short list of likely-correct encodings first (fast path),
    falls back to charset_normalizer's full detection if none of them
    produce plausible Arabic text.
    """
    path = Path(path)
    raw = path.read_bytes()

    for enc in _CANDIDATE_ENCODINGS:
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        if not _looks_corrupted(text):
            return text, enc

    # Fall back to statistical detection (handles anything unusual).
    best = from_path(path).best()
    if best is not None and not _looks_corrupted(str(best)):
        return str(best), best.encoding

    # Nothing worked — surface the failure loudly instead of silently
    # indexing garbage the way the original bug did.
    raise ValueError(
        f"Could not confidently decode {path} as Arabic text. "
        f"Tried {_CANDIDATE_ENCODINGS} and charset_normalizer's best guess "
        f"({getattr(best, 'encoding', None)}). Inspect the file manually."
    )


def rebuild_check(path: str | Path) -> None:
    """Quick CLI-style sanity check you can run against book_14.htm."""
    text, enc = read_html_text(path)
    print(f"Decoded {path} using: {enc}")
    print(f"Arabic chars found: {sum(1 for c in text if '\\u0600' <= c <= '\\u06FF')}")
    print("First 300 chars:\n", text[:300])


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python safe_read.py <path-to-book_14.htm>")
        sys.exit(1)
    rebuild_check(sys.argv[1])