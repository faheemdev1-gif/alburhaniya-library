"""Audit defects at the public boundary and source-level negative controls."""
import json
from pathlib import Path
import pytest
from app.mcp_server import search_library, get_page, get_passage, mcp
from app.services import library_db as db
from app.services.question_intent import assess_window
from app.core.evidence_blocks import blocks,body_text

FIXTURES=Path(__file__).parent/'data'

def test_repeated_pagination_is_unambiguous_everywhere():
    pages=[get_page('b01',seq) for seq in (153,193)]
    assert pages[0]['printed_page']==pages[1]['printed_page']=='70'
    assert pages[0]['citation_label']!=pages[1]['citation_label']
    for p in pages:
        assert p['page_id'] in p['citation_label']
        assert p['pagination_status']=='repeated_printed_label_unresolved'
        assert get_passage(match_id=f"{p['page_id']}-c0")['citation_label']==p['citation_label']

def test_mixed_toc_counts_search_and_round_trip_and_scope_reset():
    args=dict(query='الأوراد والقرآن',book_ids=['b41'],match_mode='exact',include_counts=True)
    for include,expected in [(False,0),(True,1),(False,0)]:
        r=search_library(**args,include_toc=include)
        assert r['returned_count']==expected
        assert r['census_matching_pages']==expected
        assert r['retrieval_completeness']['status']=='ok'
        if expected:
            h=r['results'][0]
            assert h['block_type']=='toc'
            assert get_passage(match_id=h['match_id'])['block_type']=='toc'
    assert get_passage(match_id='b41-p154-c667')['block_type']=='toc'
    assert get_passage(match_id='b41-p154-c10')['block_type']=='body'
    p=db.get_page('b41',154)
    assert {b['type'] for b in p['evidence_blocks']}=={'body','toc'}
    assert len(body_text(p['text']))==len(p['text'])

def test_poem_numbering_does_not_become_navigation():
    p=db.get_page('b14',246)
    assert all(b['type']=='body' for b in blocks(p['text']))
    assert 'b14-q091-b010' in {r.get('stable_id') for r in db.search('ربك',book_ids=['b14'],qasida_number=91)}

@pytest.mark.parametrize('cap',[1,100,1000,20001])
def test_page_cap_and_ultra_compact(cap):
    compact=get_page('b41',131,max_chars=cap)
    ultra=get_page('b41',131,max_chars=cap,mode='ultra_compact')
    assert len(compact['text'])<=compact['effective_max_chars']==min(cap,20000)
    assert compact['requested_max_chars']==cap
    assert compact['text']==ultra['text']
    assert compact['citation_label']==ultra['citation_label']
    for r in (compact,ultra):
        for k in ('timing','request_id'):r.pop(k,None)
    assert len(json.dumps(ultra))<len(json.dumps(compact))

def test_heading_and_invalid_selectors():
    r=get_passage(stable_id='b14-q007-h')
    assert r['stable_id']=='b14-q007-h' and 'bayt_number' not in r
    for args in [dict(stable_id='made-up'),dict(match_id='b41-p154-c99999'),dict(match_id='x',qasida_number=1)]:
        r=get_passage(**args)
        assert isinstance(r['error'],dict) and r['error']['retryable'] is False

def test_evidence_classification_round_trip():
    h=search_library(query='الأوراد',book_ids=['b41'],page_from=131,page_to=131,match_mode='exact')['results'][0]
    p=get_passage(match_id=h['match_id'])
    for k in ('evidence_type','evidence_type_method','evidence_type_confidence','evidence_type_scope'):
        assert h[k]==p[k]

@pytest.mark.parametrize('item',json.loads((FIXTURES/'audit_270_false_relations.json').read_text()),ids=lambda x:x['query_id']+'-'+x['match_id'])
def test_all_eighteen_false_relation_labels(item):
    p=db.get_page(item['book_id'],item['seq']);span=item['span']
    r=assess_window(item['query'],p['text'],span['start'],span['end'],db._build_exact_variant_regex)
    assert not r or r['question_relevance']!='relation_candidate'

@pytest.mark.parametrize('args',[dict(query='طمأنينة',match_mode='lexeme',min_score=1),dict(query='طمأنينة',match_mode='exact',offset=10000)])
def test_zero_result_retry_is_executable(args):
    r=search_library(**args)
    assert not r['results']
    diag=r['diagnostics'];assert diag['empty_stage'] in ('score_filter','pagination')
    assert diag['verified_retry']
    assert search_library(**diag['verified_retry'])['results']

def test_fresh_manifest_exposes_all_controls():
    schemas={t.name:t.parameters['properties'] for t in mcp._tool_manager.list_tools()}
    assert len(schemas)==5
    assert {'include_toc','include_topic_only','check_completeness'}<=schemas['search_library'].keys()
    assert {'projection','book_ids'}<=schemas['list_books'].keys()
    assert {'context_mode','max_chars'}<=schemas['get_passage'].keys()
