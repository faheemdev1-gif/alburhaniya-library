"""Deterministic, page-bounded chunks for dense retrieval."""
from __future__ import annotations

import re
from dataclasses import dataclass


_BOUNDARY_RE = re.compile(r"(?:\n\n+|(?<=[.!؟؛:])\s+|\n+|\s+)")


@dataclass(frozen=True)
class SemanticChunk:
    start_char: int
    end_char: int
    text: str


def split_semantic_chunks(
    text: str,
    *,
    target_chars: int = 450,
    overlap_chars: int = 80,
    min_chars: int = 350,
    max_chars: int = 500,
) -> list[SemanticChunk]:
    """Split one page without crossing its boundaries.

    Boundaries prefer paragraphs, Arabic/Latin sentence endings and then
    whitespace. Offsets always refer to the original page text and therefore
    remain stable match/citation anchors.
    """
    if not text:
        return []
    if not (0 <= overlap_chars < min_chars <= target_chars <= max_chars):
        raise ValueError("expected overlap < min <= target <= max")

    chunks: list[SemanticChunk] = []
    start = 0
    length = len(text)
    while start < length:
        while start < length and text[start].isspace():
            start += 1
        if start >= length:
            break

        hard_end = min(length, start + max_chars)
        if hard_end == length:
            end = length
        else:
            preferred_end = min(length, start + target_chars)
            candidates = [
                match.end()
                for match in _BOUNDARY_RE.finditer(
                    text, start + min_chars, hard_end
                )
            ]
            before_target = [value for value in candidates if value <= preferred_end]
            end = max(before_target or candidates or [hard_end])

        while end > start and text[end - 1].isspace():
            end -= 1
        if end <= start:
            end = min(length, start + max_chars)
        chunks.append(SemanticChunk(start, end, text[start:end]))
        if end >= length:
            break

        next_start = max(start + 1, end - overlap_chars)
        # Move to the next word boundary without consuming more than the
        # intended overlap.
        while next_start < end and not text[next_start].isspace():
            next_start += 1
        start = next_start

    return chunks
