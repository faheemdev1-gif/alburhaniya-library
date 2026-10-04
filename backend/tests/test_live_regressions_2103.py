"""Source-grounded regressions from the deployed 2.10.2 connector review."""
from app.core import result_cache
from app.mcp_server import search_library


def search(query):
    result_cache.clear()
    return search_library(query=query, limit=5)


def ids(response):
    return [(hit['book_id'], hit['seq']) for hit in response['results']]


def test_generic_prayer_word_cannot_answer_phone_ruling():
    response = search('ما حكم استعمال الهاتف في الصلاة')
    assert response['completion'] == 'full'
    assert response['evidence_strength'] == 'weak'
    assert not response['results']


def test_companionship_source_survives_question_frame():
    for query in ('لماذا تعد صحبة الصالحين مهمة للمريد',
                  'ما فائدة صحبة الصالحين',
                  'ما أثر مصاحبة الصالحين على قلب المريد',
                  'هل يحتاج السالك إلى صحبة الشيخ والإخوان',
                  'لماذا تنفع ملازمة الشيخ للسالك'):
        response = search(query)
        assert response['completion'] == 'full'
        assert ('b44', 43) in ids(response)


def test_attached_conjunction_preserves_distinct_comparison_subjects():
    for query in ('ما معنى الإخلاص وكيف يختلف عن الرياء',
                  'ما الفرق بين الإخلاص والرياء',
                  'كيف يختلف الإخلاص عن الرياء',
                  'كيف أميز بين الإخلاص والرياء'):
        response = search(query)
        assert response['completion'] == 'full'
        assert ('b07', 134) in ids(response)
        hit = next(h for h in response['results'] if (h['book_id'], h['seq']) == ('b07', 134))
        assert hit['question_relevance'] == 'relation_candidate'


def test_one_sided_comparison_is_explicitly_weak():
    response = search('كيف يميز السالك بين الإلهام والوسواس')
    assert response['completion'] == 'full'
    assert response['evidence_strength'] == 'weak'
    assert response['results']
    # Each hit names the one side it supports; both sides are surfaced (the
    # waswās passages were previously hidden behind a duplicated glossary hit).
    assert all(h['question_relevance'] == 'topic_only' and h['comparison_side'] in (['الإلهام'], ['الوسواس'])
               for h in response['results'])
    assert {s for h in response['results'] for s in h['comparison_side']} == {'الإلهام', 'الوسواس'}


def test_distress_question_finishes_normal_pipeline():
    response = search('ما النصيحة لمن يشعر بالهم والحزن')
    assert response['completion'] == 'full'
    assert response['results']


def test_phone_ruling_paraphrases_do_not_invent_answer():
    for query in ('هل استعمال الهاتف أثناء الصلاة جائز',
                  'ما حكم استخدام الجوال أثناء الصلاة',
                  'هل الهاتف المحمول يبطل الصلاة'):
        response = search(query)
        assert response['completion'] == 'full'
        assert response['evidence_strength'] == 'weak'
        assert not any(h['question_relevance'] == 'relation_candidate' for h in response['results'])
