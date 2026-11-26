from app.mcp_server import search_library
from app.services.urdu_questions import discovery_question
from app.services.semantic_search import combine_candidates
from app.services.query_language import comparison_subjects


def test_urdu_condition_discloses_gloss_and_preserves_source():
    query = 'سچی توبہ کی شرائط کیا ہیں؟'
    response = search_library(query=query, limit=5, detail='full')
    assert response['query_plan'][0]['original_query'] == query
    assert response['discovery_query'] == 'ما شروط التوبة النصوح'
    assert any((r['book_id'], r['seq']) in {('b39', 94), ('b44', 43)}
               for r in response['results'])
    assert not response['answer_verified']


def test_urdu_gloss_requires_complete_subject_and_relation():
    assert discovery_question('صبر کا مطلب کیا ہے؟') == 'ما معنى الصبر'
    assert discovery_question('صبر اور خوف کا مطلب کیا ہے؟') is None
    assert discovery_question('توبہ کی شرائط کیا نہیں ہیں؟') is None


def test_social_disagreement_does_not_compare_the_participants():
    assert not comparison_subjects('ما أدب الكلام عند الخلاف بين المريد وإخوانه؟')
    assert comparison_subjects('ما الفرق بين الخوف والرجاء؟')


def test_expanded_lexeme_requires_source_verification():
    hit = dict(book_id='b07', seq=1, score=.9, source_tier=1,
               match_type='lexeme', snippet='…')
    result, = combine_candidates('ذكر', [('lexeme', [hit])], [])
    assert result['verification_required'] and not result['citation_verified']
