"""Reliability of incremental checkpoints and distinct question subjects."""
from copy import deepcopy
import pytest
from app.core.search_trace import SearchTrace
from app.services.concept_links import linked_support
from app.core import result_cache
from app.mcp_server import search_library
from app.services import library_db as db
from app.services.compact_response import decode_search_response

def test_incremental_checkpoint_preserves_nested_immutability_and_replaces_page():
    trace=SearchTrace()
    first={'book_id':'b01','seq':1,'score':.2,'evidence_span':{'source_quote':'original'}}
    trace.publish([first],'literal')
    second={'book_id':'b02','seq':3,'score':.3,'support':{'review_status':'unreviewed'}}
    trace.publish_row(second,'validated')
    first['evidence_span']['source_quote']='mutated'
    second['support']['review_status']='mutated'
    update={'book_id':'b01','seq':1,'score':.8,'evidence_span':{'source_quote':'better'}}
    trace.publish_row(update,'validated')
    update['score']=0
    snapshot=trace.evidence()
    assert len(snapshot)==2 and snapshot[0]['score']==.8
    assert snapshot[0]['evidence_span']['source_quote']=='better'
    assert snapshot[1]['support']['review_status']=='unreviewed'
    snapshot[0]['score']=1
    assert trace.evidence()[0]['score']==.8

def test_checkpoint_ids_remain_unique_after_trace_events_are_capped():
    trace=SearchTrace();seen=set()
    for index in range(200):
        trace.publish_row({'book_id':'b01','seq':1,'score':index},'validated')
        assert trace.checkpoint_id not in seen
        seen.add(trace.checkpoint_id)
    assert len(trace.snapshot()['events'])<=128

def test_build_time_lexeme_spellings_preserve_every_safe_surface(tmp_path):
    import sqlite3
    from app.services.evidence_units import build_lexeme_spellings
    from app.core.arabic_utils import normalize_search_text
    with sqlite3.connect(tmp_path/'vocab.db') as conn:
        conn.execute('CREATE TABLE pages(norm_text TEXT)')
        texts=['أشرقت اشرقت والإخلاص وسوسة وسوسه','وسوسة الثناء']
        conn.executemany('INSERT INTO pages VALUES(?)',[(t,) for t in texts])
        build_lexeme_spellings(conn)
        actual=set(conn.execute('SELECT normalized,surface FROM lexeme_spellings'))
        expected={(normalize_search_text(t,level='broad'),t) for text in texts for t in text.split()}
        assert actual==expected

@pytest.mark.parametrize('text',[
    'اللهم إني خرجت ابتغاء مرضاتك ولا رياء ولا سمعة.',
    'سمع الناس مدحه فوقع في الرياء والسمعة.',
    'رياء وسمعة في عبادته.'
])
def test_shared_negative_alias_cannot_satisfy_positive_sincerity(text):
    assert linked_support('كيف أتخلص من حب الثناء وأخلص في عبادتي',text) is None

def test_distinct_sincerity_and_praise_evidence_remains_discoverable():
    text='من ادعى الإخلاص ولم يتواضع فهو كاذب وعمله رياء وسمعة.'
    result=linked_support('كيف أتخلص من حب الثناء وأخلص في عبادتي',text)
    assert result and result[3]==['sincerity','praise_desire']
    assert 'الإخلاص' in text[result[1]:result[2]]

@pytest.mark.parametrize('query,expected',[
    ('ماذا ينال من يحب سيدنا محمد',('b01',62)),
    ('كيف أتخلص من حب الثناء وأخلص في عبادتي',('b07',134)),
])
def test_specific_subjects_reach_early_source_validated_candidates(query,expected):
    result_cache.clear()
    r=search_library(query=query,limit=5,detail='full')
    assert not r.get('error') and r['completion']=='full'
    assert expected in {(h['book_id'],h['seq']) for h in r['results'][:5]}
    units=r['candidate_manifest'][0]['units']
    assert any((u['book_id'],u['seq'])==expected for u in units[:25])
    for hit in decode_search_response(r)['results']:
        span=hit['evidence_span'];text=db.get_page(hit['book_id'],hit['seq'])['text']
        assert text[span['start']:span['end']]==span['source_quote']
        assert hit['answer_verified'] is False
