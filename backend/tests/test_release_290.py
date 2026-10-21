"""Concrete regressions from the 2.8 assessment; no accuracy certification."""
import asyncio,time
from unittest.mock import patch
from app.mcp_server import search_library,get_passage
from app.services import library_db as db
from app.services.question_search import deduplicate,dialogue_at
from app.services.query_language import language_plan,morphological_forms
from app.core.budget import DEADLINE

def test_question_prefix_preserves_literal_witnesses():
 bare=search_library(query='الحقيقة المحمدية',limit=5);framed=search_library(query='ما هي الحقيقة المحمدية',limit=5,detail='full')
 assert {(h['book_id'],h['seq']) for h in bare['results']} <= {(h['book_id'],h['seq']) for h in framed['results']}
def test_reported_tawassul_and_prayer_span():
 r=search_library(query='ما حكم زيارة قبور الأولياء والتوسل بهم',limit=5);assert ('b07',256) in {(h['book_id'],h['seq']) for h in r['results']}
 r=search_library(query='كيف أحافظ على الصلاة في وقتها',limit=5);hit=next(h for h in r['results'] if h['book_id']=='b07' and h['seq']==166)
 assert 'الصلوات في أوقاتها' in hit['excerpt'];assert 'الصلوات في أوقاتها' in get_passage(match_id=hit['match_id'])['passage']
def test_language_preserves_domain_and_discloses_drops():
 p=language_plan('كيف يحفظ المريد أوراده مع الشيخ');assert 'المريد' in p['terms'] and 'الشيخ' in p['terms'] and 'كيف' in p['dropped_function_words']
 assert 'كيف' in language_plan('كيف المريد',keep_terms=['كيف'])['terms'];assert 'اخر' in morphological_forms('مااخرهاش')
def test_question_diagnostics_never_call_census():
 with patch.object(db,'search_stats',side_effect=AssertionError('question census')):r=db.zero_result_diagnostics(['كيف ززززز ززظظظ'],attempted_modes=['subject_phrase','reformulated'])
 assert all(x['frequency_scope']=='whole_corpus_precomputed_not_scoped_census' for x in r['per_term'])
def test_sequence_only_and_dialogue_evidence():
 for seq in (153,193):
  p=db.get_page('b01',seq);assert f'b01-p{seq}' in p['citation_label'] and '70' not in p['citation_label']
 text='سؤال : هل هذه أحاديث؟\nالجواب : هذا شرح للمسألة.';assert db.evidence_type(text,25,30)=='dialogue';assert dialogue_at(text,30)['speaker'] is None
def test_final_score_sort():
 r=db.search(query='مرتبة الإنسان الكامل',book_ids=['b12'],ranking='relevance',limit=20);assert [h['score'] for h in r]==sorted((h['score'] for h in r),reverse=True)
def test_mawlid_status_consistent():
 r=search_library(query='إيه رأي مولانا في الاحتفال بالمولد النبوي',limit=5);assert r['results'] and r['reformulation_status']!='not_needed'
def test_exclusive_timing_and_inherited_fields():
 r=search_library(query='ما هي الحقيقة المحمدية',limit=5,detail='full');t=r['timing'];assert abs(sum(t['phases_ms'].values())-t['total_ms'])<.01
 assert all('citation_label' in h and 'answer_verified' in h for h in [{**r.get('result_defaults',{}),**x} for x in r['results']])
def test_discovery_source_offsets():
 c=db._connection();assert c.execute('SELECT COUNT(*) FROM discovery_topics').fetchone()[0]>=150
 rows=c.execute("SELECT d.start_char,d.end_char,d.question,p.text FROM discovery_passages d JOIN pages p ON p.id=d.page_id WHERE d.kind='answer' LIMIT 20").fetchall();assert rows and all(0<=r[0]<r[1]<=len(r[3]) and r[2] for r in rows)
 assert c.execute("SELECT COUNT(*) FROM discovery_topics WHERE review_status<>'unreviewed'").fetchone()[0]==0
def test_duplicate_retains_locator():
 text='هذا نص طويل يتكرر في مصدر آخر وفيه كلام كثير عن معنى العلم والعمل والصدق واليقين والمحبة والرحمة والذكر والطاعة والسلوك والأدب والخير والفضل والنور والسلام'
 rows=[{'snippet':text,'book_id':b,'seq':s,'match_id':f'{b}-p{s}-c0','citation_label':b} for b,s in [('b39',5),('b42',4)]];r=deduplicate(rows);assert len(r)==1 and r[0]['also_in'][0]['book_id']=='b42'
def test_expired_budget_scoped():
 token=DEADLINE.set(time.monotonic()-1)
 try:r=search_library(query='الحقيقة المحمدية')
 finally:DEADLINE.reset(token)
 assert r['error']['code']=='time_budget_exceeded' and r['truncated_by_budget'];assert search_library(query='الحقيقة المحمدية')['results']
def test_authenticated_quotas_per_client(tmp_path):
 from starlette.testclient import TestClient
 from starlette.applications import Starlette
 from starlette.responses import JSONResponse
 from starlette.routing import Route
 from app.core.machine_http import MachineHTTP
 from app.core.config import Settings
 app=Starlette(routes=[Route('/mcp/',lambda request:JSONResponse({'ok':True}))]);app.add_middleware(MachineHTTP);settings=Settings(mcp_api_keys='one,two',mcp_requests_per_minute=1,rate_limit_db_path=str(tmp_path/'quota.db'))
 with patch('app.core.machine_http.get_settings',return_value=settings),TestClient(app) as client:
  assert client.get('/mcp/',headers={'Authorization':'Bearer one'}).status_code==200
  r=client.get('/mcp/',headers={'Authorization':'Bearer one'});assert r.status_code==429 and 'retry-after' in r.headers and r.json()['error']['data']['remaining_budget']==0
  assert client.get('/mcp/',headers={'Authorization':'Bearer two'}).status_code==200
def test_sync_sdk_work_does_not_block_loop():
 from mcp.server.fastmcp import FastMCP
 from app.core.machine_http import enable_threaded_tools
 m=FastMCP('test')
 @m.tool()
 def slow()->dict:time.sleep(.2);return {'ok':True}
 enable_threaded_tools(m)
 async def run():
  task=asyncio.create_task(m.call_tool('slow',{}));start=time.monotonic();await asyncio.sleep(.025);delay=time.monotonic()-start;await task;return delay
 assert asyncio.run(run())<.15
