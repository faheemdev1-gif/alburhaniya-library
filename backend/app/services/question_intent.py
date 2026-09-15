"""Versioned, conservative question discovery; never a verified-answer classifier.

Only discovery uses these aliases. Exact/lexeme searches and occurrence counts
continue to use their original literal contracts. Negation is not removed.
"""
from app.core.arabic_utils import ARABIC_STOPWORDS, safe_tokens, normalize_search_text

POLICY = "local-question-facets-v1"
FUNCTION_WORDS = ARABIC_STOPWORDS | {
    "هل", "كيف", "ماذا", "متي", "متى", "اين", "أين", "لماذا", "التي",
    "عليه", "عليها", "عليهم", "له", "لها", "لهم", "على", "إلى", "أن", "إن",
    "وما", "وهو", "وهي", "هذا", "هذه", "ذلك", "تلك", "هو", "هي",
}
_FUNCTION_KEYS = {normalize_search_text(x, level="broad") for x in FUNCTION_WORDS}


def content_terms(query):
    return list(dict.fromkeys(t for t in safe_tokens(query)
        if normalize_search_text(t, level="broad") not in _FUNCTION_KEYS))


def livelihood_intent(query):
    tokens = {normalize_search_text(t, level="broad") for t in content_terms(query)}
    return bool(tokens & {"الرزق", "رزق", "المعيشه", "معيشه"}) and bool(
        tokens & {"سعه", "توسعه", "زياده", "ضيق", "ضاقت", "تيسير", "ينال", "يجلب"})


def discovery_phrases(queries, limit=6):
    phrases = []
    for query in queries:
        tokens = content_terms(query)
        if len(tokens) < 4:
            continue
        candidates = (["سعة الرزق", "تيسير الرزق", "طلب الرزق", "الفقر", "الرزق", "ضيق"]
                      if livelihood_intent(query) else
                      [*reversed([" ".join(tokens[i:i+2]) for i in range(len(tokens)-1)]),
                       *reversed(tokens)])
        for phrase in candidates:
            if len(phrase) >= 3 and phrase not in phrases:
                phrases.append(phrase)
    return phrases[:max(1, min(int(limit), 8))]


def assess_window(query, text, start, end, pattern_builder):
    """Score only a source-local window around this evidence locator.

    Topic and relation candidates remain unverified: e.g. an author can reject
    a proposed practice. The caller must read/cite the passage, not infer advice.
    """
    left, right = max(0, start-350), min(len(text), end+350)
    window = text[left:right]
    terms = content_terms(query)
    matched = [t for t in terms if pattern_builder(t).search(window)]
    coverage = len(matched) / max(1, len(terms))
    if livelihood_intent(query):
        topic = [t for t in ("الرزق", "رزقه", "يرزق", "رزقه", "المعيشة", "الفقر", "الغنى")
                 if pattern_builder(t).search(window)]
        relation = [t for t in ("تيسير الرزق", "لتيسير الرزق", "طلب الرزق", "جلب الرزق",
                                "لجلب الرزق", "سعة الرزق", "زيادة الرزق", "شكا الفقر",
                                "عنه الفقر", "السعي", "ضيق", "مخرجا")
                    if pattern_builder(t).search(window)]
        if not topic:
            return None
        # Poverty/wealth alone is still only a topic match.
        relational = bool(relation)
        score = (0.65 if relational else 0.20) + 0.20*coverage
    else:
        if len(matched) < 2:
            return None
        topic, relation, relational = matched, [], len(matched) >= 3
        score = 0.25 + 0.60*coverage
    return {"intent_score": round(score, 6), "intent_term_coverage": round(coverage, 4),
            "question_relevance": "relation_candidate" if relational else "topic_only",
            "intent_method": POLICY, "answer_verified": False,
            "intent_evidence": {"query_terms": matched, "topic_terms": sorted(set(topic)),
                                "relation_terms": sorted(set(relation)), "start": left, "end": right}}
