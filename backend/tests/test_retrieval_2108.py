"""2.10.8: general question-understanding rules, checked on unpublished wordings.

Each rule is language-level. The wordings below were written as paraphrases
the earlier fixes had never seen; they must not be answered by adding
vocabulary keyed to these exact questions.
"""
import pytest

from app.core import result_cache
from app.mcp_server import search_library
from app.services.query_language import derived_nouns, language_plan, morphological_forms

FORGIVENESS_GROUP = {'b44-p43-c7646', 'b44-p50-c2934', 'b22-p146-c59', 'b07-p180-c740', 'b20-p145-c1381'}


def search(query, **kw):
    result_cache.clear()
    return search_library(query=query, limit=5, **kw)


def pages(response):
    return {(h['book_id'], h['seq']) for h in response['results']}


@pytest.mark.parametrize(('query', 'subjects'), [
    ('كيف يوازن المريد بين خوفه ورجائه', ['الخوف', 'الرجاء']),          # pronoun suffixes
    ('ما حال الإنسان بين خوفه من ربه ورجائه', ['الخوف', 'الرجاء']),     # prepositional modifier
    ('متى يغلب الرجاء على الخوف', ['الرجاء', 'الخوف']),                 # preference verb + على
    ('هل يقدم المريد الرجاء على الخوف', ['الرجاء', 'الخوف']),
    ('هل الأفضل للمريد الخوف أو الرجاء', ['الخوف', 'الرجاء']),          # X أو Y
    ('ما الذي يميز المرشد عن شيخ الطريقة', ['المرشد', 'شيخ الطريقة']),  # يميز X عن Y
    ('ما علاقة التوكل بالسعي', ['التوكل', 'السعي']),                    # علاقة X بY
])
def test_comparison_subjects_are_general(query, subjects):
    assert language_plan(query)['comparison_subjects'] == subjects


def test_morphology_does_not_create_homographs():
    assert 'صدق' not in morphological_forms('الصدقة')        # ta marbuta is not a pronoun
    assert 'نفاق' not in morphological_forms('الإنفاق')      # إفعال keeps its alif
    assert 'وكل' not in derived_nouns('يتوكل')               # bare root = و + كل
    assert 'الاستغفار' in derived_nouns('يستغفر')
    assert 'المجالسة' in derived_nouns('يجالس') or 'مجالسة' in derived_nouns('يجالس')
    assert 'الوسواس' in derived_nouns('الوسوسه')


@pytest.mark.parametrize('query', [
    'متى يغلب الرجاء على الخوف',
    'هل الأفضل للمريد الخوف أو الرجاء',
    'بماذا يرجح المريد رجاءه على خوفه',
    'كيف يتوكل العبد على ربه',
    'ما علاقة التوكل بالسعي',
])
def test_hope_and_trust_questions_do_not_return_the_forgiveness_group(query):
    ids = {h['match_id'] for h in search(query)['results']}
    assert len(ids & FORGIVENESS_GROUP) <= 2


@pytest.mark.parametrize('query', [
    'متى يغلب الرجاء على الخوف',
    'كيف يوازن المريد بين خوفه ورجائه',
    'هل يقدم المريد الرجاء على الخوف',
])
def test_fear_and_hope_paraphrases_reach_the_source(query):
    assert pages(search(query)) & {('b37', 156), ('b09', 88)}


def test_duplicate_edition_does_not_hide_other_evidence():
    response = search('ما مراتب اليقين')
    assert pages(response) & {('b13', 1), ('b13', 57), ('b41', 12), ('b42', 21)}


def test_companionship_verb_finds_companionship_not_covenant():
    response = search('لماذا يجالس المريد الصالحين')
    assert ('b25', 73) in pages(response)
    assert 'b44-p43-c2072' not in {h['match_id'] for h in response['results']}


@pytest.mark.parametrize('query', ['هل الدخان حرام عند مولانا', 'ما حكم التدخين للمريد'])
def test_smoking_wordings_find_the_only_statement_and_stay_weak(query):
    response = search(query)
    assert ('b40', 50) in pages(response)
    assert response['evidence_strength'] == 'weak'


def test_reply_after_question_mark_is_not_credited_to_questioner():
    response = search('ما رأي الشيخ في شرب السجائر', detail='full')
    hit = next(h for h in response['results'] if (h['book_id'], h['seq']) == ('b40', 50))
    assert hit.get('dialogue_role') == 'answer'
    assert hit.get('speaker') != 'السائل'


def test_single_word_virtue_question_uses_focus():
    assert ('b17', 65) in pages(search('ما فضل الاستغفار'))
