"""Versioned grammatical question families; no source IDs or answer routing.

This is a conservative rule baseline, not reviewed linguistic coverage. Unknown
relations preserve the original content route. Negation and qualifiers are kept
in the plan even when they are not retrieval anchors.
"""
import re
from app.core.arabic_utils import normalize_search_text, safe_tokens
VERSION='frames-1.0'
ROLE=r'(?:المريد|السالك|العبد|الإنسان|الشيخ|مولانا)'
RULES=(
 ('signs',r'^(?:بأي\s+شيء\s+أعرف|كيف\s+أعرف)\s+(.+)$'),
 ('signs',r'^ما\s+(?:ال)?(?:علامات|صفات|دلائل)(?:\s+التي\s+تدل\s+على)?\s+(.+)$'),
 ('condition',r'^ما\s+شروط\s+(.+?)(?=\s+(?:حتى|لكي|كي)\b|$)'),
 ('importance',r'^(?:ما\s+(?:أهمية|اهمية|فائدة)|ليه\s+مهم)\s+(.+)$'),
 ('merit',r'^ما\s+(?:فضل|ثواب|أجر)\s+(.+)$'),
 ('merit',r'^ماذا\s+ينال\s+(.+)$'),
 ('stance',r'^(?:ما\s+(?:موقف|رأي|راي|نظرة)|(?:إيه|ايه)\s+رأي)\s+(?:'+ROLE+r'\s+)?(?:من|في|إلى)?\s*(.+)$'),
 ('ruling',r'^(?:ما\s+حكم|هل\s+(?:يجوز|يصح|يمكن))\s+(.+)$'),
 ('definition',r'^ما\s+(?:معنى|حقيقة|المراد\s+ب|المقصود\s+ب)\s*(.+)$'),
 ('stages',r'^ما\s+(?:(?:هي|هو)\s+)?(?:درجات|مراتب|أنواع|اقسام|أقسام|مقامات)\s+(.+)$'),
 ('identity',r'^(?:من\s+(?:هو|هم)|ما\s+(?:دور|وظيفة))\s+(.+?)(?=\s+وما\s+|$)'),
 ('relation',r'^ما\s+(?:علاقة|صلة)\s+(.+)$'),
 ('comparison',r'^ما\s+الفرق\s+بين\s+(.+)$'),
 ('remedy',r'^كيف\s+(?:يعالج|أعالج|اتخلص|أتخلص|يتخلص|يحفظ|أحفظ)\s+(?:'+ROLE+r'\s+)?(?:من\s+)?(.+)$'),
 ('cause',r'^(?:لماذا|ليه|ما\s+سبب)\s+(.+)$'),
 ('timing',r'^(?:متى|إمتى|امتى|في\s+أي\s+وقت)\s+(.+)$'),
 ('method',r'^(?:كيف|إزاي|ازاي|بأي\s+طريقة|ماذا\s+أفعل)\s+(.+)$'),
 ('condition',r'^هل\s+يكفي\s+(.+)$'),
)

def parse_frame(query):
    q=normalize_search_text(query.strip(' ؟?'),level='safe')
    for intent,regex in RULES:
        m=re.match(regex,q)
        if not m:continue
        subject=m.group(1).strip()
        subject=re.sub(r'\s+ل(?:لمريد|لسالك)$','',subject)
        cues=[];slots=[subject]
        if intent in {'comparison','method','ruling'}:
            pair=re.search(r'\bبين\s+(.+?)\s+و\s*(.+)$',q)
            coexist=re.search(r'(.+?)\s+(مع|أثناء|وهو|وأنا)\s+(.+)$',subject)
            preference=re.search(r'(.+?)\s+(أفضل\s+من|أعلى\s+من|أولى\s+من|أو|أم)\s+(.+)$',subject)
            if preference:intent='preference';slots=[preference[1],preference[3]];cues=[preference[2]]
            elif pair:slots=list(pair.groups());cues=['بين'];intent='coexistence' if re.search(r'يجمع|نجمع',q) else 'comparison'
            elif coexist:intent='coexistence';slots=[coexist[1],coexist[3]];cues=[coexist[2]]
        if intent=='signs':
            # A derivational subject remains explicit in the plan. The lexical
            # route, not a page mapping, supplies صدق <-> صادق.
            subject=re.sub(r'\s+في\s+(?:الطريق|طريق\s+القوم)$','',subject)
            slots=[subject]
        return {'intent':intent,'slots':slots,'subject_phrase':subject,
                'frame_words':safe_tokens(q[:m.start(1)]),'cues':cues,
                'presupposition':intent=='importance','policy_version':VERSION,
                'qualifiers':q[m.end(1):].strip(),
                'negation':[t for t in safe_tokens(q) if t in {'لا','ليس','لم','لن','غير','ولا'}]}
    return None
