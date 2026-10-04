"""Public review rewordings and negative controls for source-local retrieval."""
import pytest

from app.core import result_cache
from app.mcp_server import search_library
from app.services.query_language import language_plan
from app.services.question_intent import is_question


@pytest.mark.parametrize(('query', 'subjects'), [
    ('ما الفرق بين مقام الفناء ومقام البقاء', ['الفناء', 'البقاء']),
    ('ما الفرق بين الخوف من الله والرجاء في رحمته', ['الخوف', 'الرجاء']),
    ('هل يغلّب المريد الخوف أم الرجاء', ['الخوف', 'الرجاء']),
    ('كيف نميز علم اليقين من عين اليقين', ['علم اليقين', 'عين اليقين']),
    ('كيف أميز الإخلاص الحقيقي من الرياء', ['الإخلاص', 'الرياء']),
    ('كيف يعرف المريد أن عمله لله لا لمدح الناس', ['الإخلاص', 'الرياء']),
    ('متى يصل السالك إلى البقاء بعد الفناء', ['الفناء', 'البقاء']),
])
def test_comparison_frames_retain_both_real_subjects(query, subjects):
    assert language_plan(query)['comparison_subjects'] == subjects
    assert is_question(query)


@pytest.mark.parametrize(('query', 'expected'), [
    ('ما الفرق بين مقام الفناء ومقام البقاء', {('b21', 100), ('b23', 15), ('b37', 80)}),
    ('متى يصل السالك إلى البقاء بعد الفناء', {('b21', 100), ('b23', 15), ('b37', 80)}),
    ('ما الفرق بين الخوف من الله والرجاء في رحمته', {('b37', 156)}),
    ('هل يغلّب المريد الخوف أم الرجاء', {('b37', 156)}),
    ('كيف نميز علم اليقين من عين اليقين', {('b41', 12)}),
    ('كيف أميز الإخلاص الحقيقي من الرياء', {('b07', 134)}),
    ('كيف يعرف المريد أن عمله لله لا لمدح الناس', {('b07', 134), ('b44', 19)}),
    ('ما أثر مجالسة الصالحين في تزكية نفس المريد', {('b44', 43), ('b25', 73)}),
    ('ماذا يستفيد السالك من مجالسة أهل الله', {('b44', 43), ('b25', 73)}),
    ('هل يرى المريد النبي صلى الله عليه وسلم في المنام', {('b29', 23)}),
    ('ما ثواب الصلاة على النبي', {('b12', 174), ('b30', 90)}),
])
def test_reviewed_passage_discovered_in_top_five(query, expected):
    result_cache.clear()
    result = search_library(query=query, limit=5)
    assert not result.get('error') and result['completion'] == 'full'
    assert {(h['book_id'], h['seq']) for h in result['results']} & expected


def test_smoking_bridge_is_weak_and_phone_does_not_become_a_ruling():
    for query in ('ما رأي الشيخ في شرب السجائر', 'إيه رأي مولانا في السجاير والشيشة'):
        result_cache.clear()
        result = search_library(query=query, limit=5)
        assert ('b40', 50) in {(h['book_id'], h['seq']) for h in result['results']}
        assert result['evidence_strength'] == 'weak'
        assert all(h['question_relevance'] == 'topic_only' for h in result['results'])
    result_cache.clear()
    result = search_library(query='هل استعمال الهاتف أثناء الصلاة جائز', limit=5)
    assert result['evidence_strength'] == 'weak'


def test_reward_wording_prioritizes_local_subject_and_focus():
    for query in ('ما ثواب الصلاة على النبي', 'ما فضل الصلاة على النبي صلى الله عليه وسلم'):
        result_cache.clear()
        result = search_library(query=query, limit=2)
        assert {(h['book_id'], h['seq']) for h in result['results']} == {('b12', 174), ('b30', 90)}
