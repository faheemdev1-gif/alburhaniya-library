"""2.10.9: rules from the live 2.10.8 blind check (wordings no earlier fix had seen)."""
import pytest

from app.core import result_cache
from app.mcp_server import search_library
from app.services.query_language import language_plan, morphological_forms, subject_phrase
from app.services.question_search import mask_honorifics


def search(query):
    result_cache.clear()
    return search_library(query=query, limit=5)


def pages(response):
    return {(h['book_id'], h['seq']) for h in response['results']}


def test_article_nouns_keep_their_first_letter():
    assert 'وكل' not in morphological_forms('التوكل')
    assert 'سليم' not in morphological_forms('التسليم')
    assert 'توكل' in morphological_forms('التوكل')


def test_blessing_formula_is_not_virtue_evidence():
    assert 'أفضل' not in mask_honorifics('عليه أفضل الصلاة والسلام')
    assert 'أفضل من' in mask_honorifics('الصلاة على النبى أفضل من عتق الرقاب')
    response = search('ما فضل الصلاة على سيدنا محمد')
    assert not any('أفضل الصلاة والسلام' in (h.get('excerpt') or '') and h['question_relevance'] == 'relation_candidate'
                   for h in response['results'])


@pytest.mark.parametrize(('query', 'subjects'), [
    ('كيف يجمع العبد بين خوف العقاب ورجاء الثواب', ['الخوف', 'الرجاء']),   # rare constructs reduce
    ('كيف نميز علم اليقين من عين اليقين', ['علم اليقين', 'عين اليقين']),  # established compounds stay
    ('ما الفرق بين مقام الفناء ومقام البقاء', ['الفناء', 'البقاء']),
])
def test_construct_subjects(query, subjects):
    assert language_plan(query)['comparison_subjects'] == subjects


def test_attached_preposition_and_frames():
    assert subject_phrase('ما المقصود بعين اليقين') == 'عين اليقين'
    assert subject_phrase('ما حقيقة الرياء') == 'الرياء'


@pytest.mark.parametrize(('query', 'expected'), [
    ('كيف يجمع العبد بين خوف العقاب ورجاء الثواب', {('b37', 156), ('b09', 88)}),
    ('ما المقصود بعين اليقين', {('b13', 21), ('b39', 72), ('b41', 12), ('b13', 1), ('b42', 21)}),
    ('ما فضل التوكل على الله', {('b10', 20), ('b32', 38), ('b41', 149), ('b40', 100), ('b13', 77)}),
    ('هل التدخين يضر سلوك المريد', {('b40', 50)}),
])
def test_live_blind_failures(query, expected):
    assert pages(search(query)) & expected


def test_noun_gap_still_drops_homographs():
    # A passage with only الهاتف (here a heavenly voice) is not kept when the
    # missing word is a noun (الصلاة), not a verb.
    response = search('ما حكم استعمال الهاتف في الصلاة')
    assert not response['results']
