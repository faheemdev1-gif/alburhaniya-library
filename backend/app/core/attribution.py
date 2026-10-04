"""Conservative, source-local speaker guards shared by retrieval and reading.

These heuristics identify an explicitly reported position, not its truth or
the position of the book's author. Unknown speech stays unknown.
"""
import re

REPORTED = re.compile(r"قال\s+محمد\s+بن\s+عبد\s*الوهاب|قال\s+المعترض|يقول\s+المعترض|زعموا|شبهة", re.I)
QUESTION = re.compile(r"(?:^|\n)\s*(?:سؤال|السؤال|س\s*[:：])", re.I)
ANSWER = re.compile(r"(?:^|\n)\s*(?:الجواب|جواب|ج\s*[:：])", re.I)
WARNING = "Reported position; read the surrounding response before attributing it to the author."


def attribution_at(text: str, start: int, end: int | None = None) -> dict:
    """Return a guard for the source unit containing the evidence offset.

    An explicit answer boundary stops a reported-view guard from leaking to
    the author's subsequent response. The offset remains in source characters.
    """
    start = max(0, min(int(start), len(text)))
    previous = text.rfind("\n\n", 0, start)
    left = previous + 2 if previous >= 0 else 0
    right = text.find("\n\n", start)
    if right < 0:
        right = len(text)
    unit = text[left:right]
    local = start - left
    boundaries = [(m.start(), "question") for m in QUESTION.finditer(unit)]
    boundaries += [(m.start(), "answer") for m in ANSWER.finditer(unit)]
    prior = [item for item in boundaries if item[0] <= local]
    if prior:
        boundary, role = max(prior)
        if role == "question":
            # Transcripts often give the reply right after the question mark
            # with no الجواب marker ("سؤال: ...؟ لا لا لا ..."). Evidence after
            # the question's own question mark is the reply: its speaker is
            # not inferred, and it is never credited to the questioner.
            closing = re.search(r"[؟?]", unit[boundary:local])
            if not closing:
                return {"source_role": "question", "speaker": "السائل",
                        "speaker_basis": "explicit_question_marker", "attribution_review_status": "unreviewed"}
            boundary += closing.end()
        unit = unit[boundary:]
        local -= boundary
        left += boundary
    reported = list(REPORTED.finditer(unit[:local + 1]))
    if reported and local - reported[-1].start() <= 700:
        marker = reported[-1]
        return {"source_role": "reported_view", "reported_view": True,
                "attribution_warning": WARNING,
                "attribution_basis": "explicit_report_marker_in_source_unit",
                "attribution_marker_span": {"start": left + marker.start(), "end": left + marker.end()},
                "attribution_review_status": "unreviewed"}
    return {"source_role": "unknown", "attribution_review_status": "unreviewed"}
