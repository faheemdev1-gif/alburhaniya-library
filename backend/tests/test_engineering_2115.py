"""Contracts from the uploaded specifications; no held-out score claims."""
import json,hashlib,time
from types import SimpleNamespace
from threading import Event
import anyio,pytest
from app.mcp_server import search_library,get_page,get_passage,mcp
from app.services import library_db as db
from app.core import result_cache
from app.services.compact_response import decode_search_response
from app.services.question_search import anchor_plan

@pytest.mark.parametrize('book,seq',[('b41',131),('b31',90),('b37',156),('b37',67),('b14',246)])
def test_get_page_is_the_exact_coordinate_authority(book,seq):
    raw=db.get_page(book,seq)['text'];page=get_page(book,seq)
    assert page['text']==raw
    cc=page['coordinate_contract']
    assert cc['offset_unit']=='unicode_codepoint' and cc['range']=='[start,end)'
    assert cc['text_sha256']==hashlib.sha256(raw.encode()).hexdigest()
    assert all(0<=b['start']<b['end']<=len(raw) for b in page['evidence_blocks'])

@pytest.mark.parametrize('mode',['exact','terms','lexeme','auto'])
def test_all_search_paths_have_source_resolving_quotes(mode):
    result_cache.clear()
    r=search_library(query='الخلوة' if mode!='auto' else 'ما أهمية الخلوة للسالك',match_mode=mode,limit=5,detail='full')
    assert not r.get('error') and r['results']
    for hit in decode_search_response(r)['results']:
        text=get_page(hit['book_id'],hit['seq'])['text'];span=hit['evidence_span']
        assert text[span['start']:span['end']]==span['source_quote']
        assert hit['answer_verified'] is False
        assert hit['text_version']==hashlib.sha256(text.encode()).hexdigest()[:16]
        for segment in hit.get('speaker_segments',[]):
            assert 0<=segment['start']<segment['end']<=len(text)

@pytest.mark.parametrize('query,mode',[('الخلوة','exact'),('ما أهمية الخلوة للسالك','auto'),('الأوراد','lexeme')])
def test_ultra_and_compact_preserve_evidence_and_provenance(query,mode):
    outputs=[]
    for projection in ('compact','ultra_compact'):
        result_cache.clear()
        r=search_library(query=query,match_mode=mode,mode=projection,detail='full',limit=5)
        assert not r.get('error')
        outputs.append(decode_search_response(r))
    assert outputs[0]==outputs[1]

@pytest.mark.parametrize('query,expected',[
 ('ما العلامات التي تدل على صدق المريد في الطريق',{('b07',138),('b16',37)}),
 ('كيف يجمع السالك بين خشية الله والأمل في عفوه',{('b37',156),('b07',150)}),
 ('كيف يكون اتصال المريد بالمشايخ بالفواتح',{('b37',67),('b15',31)}),
 ('ما شروط التوبة حتى لا تكون مجرد كلام باللسان',{('b39',94),('b44',43)}),
 ('إذا تركت وردي مدة فهل أعود للاسم الذي كنت فيه',{('b15',26)}),
 ('إذا آذاني أخ في الطريقة فكيف أجيبه من غير خصومة',{('b44',3),('b19',21)}),
 ('هل البيع والشراء يمنعان العبد من ذكر الله بقلبه',{('b28',39),('b27',4),('b41',134)}),
])
def test_disclosed_failure_families(query,expected):
    result_cache.clear();r=search_library(query=query,limit=5,detail='full')
    assert r['status']['execution']=='full' and not r.get('error')
    assert {(x['book_id'],x['seq']) for x in r['results']} & expected
    assert r['route_funnels'] and all('cap_reached' in f for f in r['route_funnels'])
    assert all('routes' in f for f in r['route_funnels'])


def test_conditions_keep_qualifiers_and_relation_without_modifier_as_subject():
    plan=anchor_plan('ما شروط التوبة حتى لا تكون مجرد كلام باللسان')
    assert plan['question_frame']['intent']=='condition'
    assert 'لا' in plan['question_frame']['negation']
    assert plan['subject_phrase']=='التوبة'
    assert not {'مجرد','شروط','حتى'} & set(plan['anchors'])


def test_unreliable_printed_labels_are_not_published():
    r=search_library(query='الله',book_ids=['b01'],page_from=153,page_to=153,match_mode='exact',limit=2)
    assert all(x.get('printed_page') is None for x in r['results'])
    assert get_page('b01',153).get('printed_page') is None
    assert get_passage(match_id='b01-p153-c0').get('printed_page') is None


def test_source_units_are_build_time_and_bounded():
    conn=db._connection()
    assert conn.execute('SELECT COUNT(*) FROM evidence_units').fetchone()[0]>20000
    for u in conn.execute('SELECT e.*,p.text FROM evidence_units e JOIN pages p ON p.id=e.page_id WHERE e.id%101=0'):
        quote=u['text'][u['start_char']:u['end_char']]
        assert hashlib.sha256(quote.encode()).hexdigest()==u['text_sha256']


def test_supervisor_returns_checkpoint_and_worker_cooperates(monkeypatch):
    from app.core.machine_http import enable_threaded_tools
    from app.core.search_trace import checkpoint,CURRENT_TRACE,stage
    from app.core.config import get_settings
    from app.services.hit_contract import canonical_hit
    settings=get_settings();monkeypatch.setattr(settings,'request_budget_seconds',.10)
    row=db.search(query='الخلوة',limit=1)[0]
    row=canonical_hit(row,db.get_page(row['book_id'],row['seq']))
    stopped=Event()
    def search_library(**kwargs):
        trace=CURRENT_TRACE.get();checkpoint([row],'lexical_validation');stage('optional_rerank')
        while not trace.cancelled.is_set():time.sleep(.002)
        stopped.set()
        return {'late':True}
    tool=SimpleNamespace(is_async=False,fn=search_library)
    server=SimpleNamespace(_tool_manager=SimpleNamespace(list_tools=lambda:[tool]))
    enable_threaded_tools(server)
    async def invoke():return await tool.fn(query='الخلوة',limit=1,detail='full')
    r=anyio.run(invoke)
    assert r['completion']=='partial' and r['results']
    assert r['status']['evidence_status']=='candidates'
    assert r['diagnostics']['active_stage']=='optional_rerank'
    assert r['diagnostics']['checkpoint_id'] and stopped.wait(.25)


def test_empty_timeout_is_unknown_not_success(monkeypatch):
    from app.core.search_trace import SearchTrace,partial_response
    trace=SearchTrace();trace.start('candidate_sql')
    r=partial_response(trace,{'query':'مجهول','limit':5})
    assert r['status']=={'execution':'partial','evidence_status':'unknown_due_to_budget'}
    assert not r['results'] and r['error']['code']=='time_budget_exceeded'
