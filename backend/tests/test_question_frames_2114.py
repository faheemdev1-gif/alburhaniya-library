"""Public failure families from the engineering audit, plus scope controls."""
from app.services.question_search import SEARCH_STATE, anchor_plan, search_questions


def test_frame_words_do_not_displace_the_subject():
    for query, word in [('ما أهمية الخلوة للسالك', 'أهمية'),
                        ('ما موقف الشيخ من البدع', 'موقف'),
                        ('ما علامات المريد الصادق', 'علامات')]:
        parsed = anchor_plan(query)
        assert word not in parsed['anchors']
        assert parsed['question_frame']['intent'] in ('importance', 'stance', 'signs')


def test_premise_correction_and_sincere_disciple_are_ranked():
    khalwa = search_questions(query='ما أهمية الخلوة للسالك', limit=5)
    assert (khalwa[0]['book_id'], khalwa[0]['seq']) == ('b31', 90)
    assert khalwa[0]['corrects_premise'] is True
    signs = search_questions(query='ما علامات المريد الصادق', limit=5)
    assert (signs[0]['book_id'], signs[0]['seq']) == ('b07', 138)


def test_preference_retains_alternatives_but_does_not_claim_preference():
    query='هل الأفضل للمريد أن يخشى الله أو يطمع في رحمته'
    parsed=anchor_plan(query)
    assert parsed['comparison_subjects'] == ['الخشية', 'الرجاء']
    assert parsed['question_frame']['cues'] == ['أو']
    hits=search_questions(query=query, limit=5)
    assert any((h['book_id'],h['seq']) == ('b37',156) for h in hits)
    assert all(h['question_relevance']=='topic_only' for h in hits)
    assert SEARCH_STATE.get()['evidence_strength']=='weak'


def test_subject_fallback_never_escapes_scope_or_promotes_to_answer():
    query='ما أهمية الخلوة للسالك'
    scoped=search_questions(query=query,book_ids=['b01'],limit=5)
    assert all(h['book_id']=='b01' for h in scoped)
    absent=search_questions(query='ما أهمية الزورق الفضائي للسالك',limit=5)
    assert not absent or all(h['question_relevance']=='topic_only' for h in absent)
