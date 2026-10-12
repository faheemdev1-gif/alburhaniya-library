from app.services.question_search import SEARCH_STATE, search_questions
from scripts.score_retrieval_10 import score
import pytest


def test_pride_query_excludes_age_and_size_readings():
    rows = search_questions(query='كيف يتخلص السالك من الكبر', limit=5)
    assert rows
    assert not any((r['book_id'], r['seq']) in {('b14', 69), ('b13', 172), ('b32', 56), ('b22', 215)} for r in rows)


def test_children_mentions_remain_weak_and_scoped():
    rows = search_questions(query='كيف أربي أبنائي تربية صالحة', limit=5)
    assert rows and all(r['book_id'] == 'b44' and r['question_relevance'] == 'topic_only' for r in rows)
    assert SEARCH_STATE.get()['evidence_strength'] == 'weak'
    scoped = search_questions(query='كيف أربي أبنائي تربية صالحة', book_ids=['b07'])
    assert not scoped


def test_ten_gate_rejects_public_only_or_ungraded_claims():
    with pytest.raises(ValueError, match='300 answerable intents'):
        score({'owner': 'independent reviewer', 'release': '2.10.13', 'questions': []})
    with pytest.raises(ValueError, match='independent review'):
        score({'owner': 'independent reviewer', 'release': '2.10.13',
               'questions': [{'intent_id': '1', 'query': 'ما معنى الكبر'}]})
