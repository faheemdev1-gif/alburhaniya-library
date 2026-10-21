"""Conservative, source-local speaker guards shared by retrieval and reading.

These heuristics identify an explicitly reported position, not its truth or
the position of the book's author. Unknown speech stays unknown.
"""
import re

REPORTED = re.compile(r"قال\s+محمد\s+بن\s+عبد\s*الوهاب|قال\s+المعترض|يقول\s+المعترض|زعموا|شبهة", re.I)
QUESTION = re.compile(r"(?:^|\n)\s*(?:سؤال|السؤال|س\s*[:：])", re.I)
ANSWER = re.compile(r"(?:^|\n)\s*(?:الجواب|جواب|ج\s*[:：])", re.I)
WARNING = "Reported position; read the surrounding response before attributing it to the author."
SPEAKER_MARKER = re.compile(r"(?<![ء-ي])(?P<label>السائل(?:\s*\([^)]{1,30}\))?|مولانا\s+الشيخ|سيدي\s+فخر\s+الدين|الشيخ|سؤال|الجواب|جواب|س|ج)\s*[:：]")


def speaker_span(text: str, start: int, end: int) -> dict:
    """Canonical code-point segments; question/answer markers stay whole."""
    start=max(0,min(start,len(text)));end=max(start,min(end,len(text)))
    marks=list(SPEAKER_MARKER.finditer(text));events=[]
    for i,m in enumerate(marks):
        label=m.group('label');question=label.startswith(('السائل','سؤال')) or label=='س'
        role='question' if question else 'answer'
        name='السائل' if question else label if 'الشيخ' in label or 'فخر' in label else None
        events.append((m.start(),role,name,'explicit_marker' if name else 'structural'))
        if question:
            stop=marks[i+1].start() if i+1<len(marks) else len(text)
            close=re.search(r'[؟?]',text[m.end():stop])
            if close:events.append((m.end()+close.end(),'answer',None,'structural'))
    events.sort();positions=sorted({start,end,*[pos for pos,_,_,_ in events if start<pos<end]})
    segments=[]
    for a,b in zip(positions,positions[1:]):
        prior=next((e for e in reversed(events) if e[0]<=a),None)
        if prior is None or not text[a:b].strip():continue
        _,role,name,basis=prior
        segments.append({'start':a,'end':b,'role':role,'speaker':name,'basis':basis})
    if not segments:return {}
    if len({(x['role'],x['speaker']) for x in segments})>1:
        return {'speaker':'mixed','dialogue_role':'mixed','speaker_segments':segments,
                'speaker_basis':'explicit_markers_in_span'}
    first=segments[0]
    return {'speaker':first['speaker'],'dialogue_role':first['role'],
            'speaker_segments':segments if len(segments)>1 else [],'speaker_basis':first['basis']}


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
