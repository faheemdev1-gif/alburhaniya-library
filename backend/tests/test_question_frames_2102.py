"""Unseen question frames must not select unrelated fixed topic groups."""
from app.core import result_cache
from app.mcp_server import search_library
from app.services.query_language import language_plan
from app.services.question_intent import plan


def test_role_word_does_not_override_subject():
    assert plan('ما حكم التدخين عند الشيخ')['required'] == []
    assert language_plan('ما حكم التدخين عند الشيخ')['subject_phrase'] == 'التدخين'
    result_cache.clear()
    result = search_library(query='ما حكم التدخين عند الشيخ', limit=5)
    assert result['evidence_strength'] == 'weak'
    assert result['results']
    assert all(hit['question_relevance'] == 'topic_only' for hit in result['results'])


def test_comparison_retains_two_subjects_in_different_frames():
    for query in ('كيف يفرق الشيخ بين الفناء والبقاء',
                  'ما الفرق بين الفناء والبقاء عند الصوفية',
                  'ما معنى الإخلاص وكيف يختلف عن الرياء'):
        subjects = language_plan(query)['comparison_subjects']
        assert len(subjects) == 2 and subjects[0] != subjects[1]
        assert plan(query)['required'] == []
    result = search_library(query='كيف يفرق الشيخ بين الفناء والبقاء', limit=5)
    assert ('b21', 100) in [(h['book_id'], h['seq']) for h in result['results']]


def test_literal_count_does_not_inherit_discovery_variants():
    result = search_library(query='التدخين', match_mode='exact',
                            include_counts=True, limit=5)
    assert result['literal_matching_pages'] == 0
