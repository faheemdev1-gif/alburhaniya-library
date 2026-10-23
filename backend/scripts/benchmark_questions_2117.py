"""Controlled local comparison; tight budgets are synthetic, never live scores."""
import json,logging,time,math,os,sys,argparse
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline-code',type=Path,help='Optional folder containing a baseline app package')
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
sys.path.insert(0,str((args.baseline_code or ROOT).resolve()))
from app.mcp_contract import SERVER_VERSION
from app.core import result_cache
from app.core.budget import DEADLINE
from app.core.search_trace import CURRENT_TRACE,SearchTrace
from app.services import library_db as db
from app.services.question_intent import CONCEPTS,concept_regex
from app.services.concept_links import CONCEPT_FORMS,source_pattern
from app.services.question_search import search_questions,SEARCH_STATE
from app.mcp_server import search_library
logging.getLogger('app.services.traffic_metrics').setLevel(logging.WARNING)
dest=args.output.resolve();dest.parent.mkdir(parents=True,exist_ok=True)
fixtures=json.loads((ROOT/'tests/data/engineering_spec_fixtures_2115.json').read_text())['fixtures']
questions=[f for f in fixtures if f['proposed_expected_outcome'].get('source_pages_any')]
preparation=time.perf_counter()
for name in CONCEPTS:concept_regex(name)
for name in CONCEPT_FORMS:source_pattern(name)
preparation=(time.perf_counter()-preparation)*1000
def hits(rows,f):
 expected=f['proposed_expected_outcome']['source_pages_any']
 return any(h['book_id']+'-p'+str(h['seq']) in expected for h in rows[:5])
rows=[]
for budget in [5.,.25]:
 for repeat in range(3):
  for f in questions:
   trace=SearchTrace();tt=CURRENT_TRACE.set(trace);dt=DEADLINE.set(time.monotonic()+budget)
   start=time.perf_counter()
   try:
    result=search_questions(**f['recorded_arguments'],ranking='primary_first')
    state=SEARCH_STATE.get()
    rows.append({'id':f['fixture_id'],'budget_s':budget,'repeat':repeat,'ms':round((time.perf_counter()-start)*1000,3),'source_page_hit':hits(result,f),'completion':state['completion'],'checkpoint_count':len(trace.evidence()),'locators':[h['match_id'] for h in result[:5]]})
   finally:DEADLINE.reset(dt);CURRENT_TRACE.reset(tt)
scope=next(f for f in fixtures if f['fixture_id']=='R13_T10_F_WASWAS_FALSE_HIT_SCOPED')
result_cache.clear();t=time.perf_counter();scoped=search_library(**scope['recorded_arguments'],detail='full');scoped_ms=(time.perf_counter()-t)*1000
summaries=[]
for budget in [5.,.25]:
 cases=[r for r in rows if r['budget_s']==budget];times=sorted(r['ms'] for r in cases)
 summaries.append({'budget_s':budget,'calls':len(cases),'source_page_hits':sum(r['source_page_hit'] for r in cases),'full':sum(r['completion']=='full' for r in cases),'partial':sum(r['completion']=='partial' for r in cases),'median_ms':times[len(times)//2],'p95_ms':times[math.ceil(.95*len(times))-1]})
out={'version':SERVER_VERSION,'scope':'Controlled local direct question pipeline with new immutable trace per call, fixed language patterns precompiled for both versions, no answer-cache reuse, 18 disclosed questions repeated 3 times per budget. 0.25-second budget is a synthetic stress condition, not Render or independent answer grading.','precompile_ms':round(preparation,3),'summaries':summaries,'first_scoped_lexeme_ms':round(scoped_ms,3),'scoped_lexeme_response':scoped,'cases':rows}
dest.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ['cases','scoped_lexeme_response']},indent=2))

