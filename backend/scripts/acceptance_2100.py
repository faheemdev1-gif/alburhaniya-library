#!/usr/bin/env python3
"""Reproducible local acceptance. These are not live deployment measurements."""
import ast,json,sys,time,math,statistics,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT));os.chdir(ROOT)
from app.mcp_server import search_library,list_books
from app.core import result_cache

def percentile(xs,p=.95):return sorted(xs)[max(0,math.ceil(len(xs)*p)-1)] if xs else None

def main():
 old=json.loads((ROOT/'tests/data/audit_270_regressions.json').read_text())['suite']
 new=next(ast.literal_eval(n.value) for n in ast.parse((ROOT/'scripts/verify_release_2100.py').read_text()).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='NEW' for t in n.targets))
 cases=[{'id':r['id'],'query':r['query']} for r in old if r['id'] in ['L1','L2','W1','W2','W4','P1','P2','A1','A2','Q1','Q2','S1','S2']]+[{'id':f'H{i+1}','query':q} for i,q in enumerate(new)]
 runs=[]
 for cycle in range(5):
  for case in cases:
   result_cache.clear()
   for state in ['response_cache_cold','warm']:
    t=time.perf_counter();r=search_library(query=case['query'],limit=5);elapsed=time.perf_counter()-t
    runs.append({**case,'cycle':cycle+1,'state':state,'seconds':round(elapsed,6),'ok':not r.get('error'),'nonempty':bool(r.get('results')),'completion':r.get('completion','full'),'cache':r.get('cache'),'timing':r.get('timing'),'request_id':r.get('request_id'),'result_ids':[(h['book_id'],h['seq']) for h in r.get('results',[])]})
  print('Cycle',cycle+1,'finished',flush=True)
 phrases=['الهم والحزن','الحقيقة المحمدية','ليلة القدر','الفناء والبقاء','البقاء بعد الفناء','تربية الأبناء','تربية الأطفال','الصلاة على النبي','الصلاة في وقتها','كسب العيش','طلب الرزق','سعة الرزق','ضيق الصدر','حفظ اللسان','كظم الغيظ','بر الوالدين','المولد النبوي','زيارة القبور','الذكر الكثير','تلاوة القرآن','قراءة الأوراد','آداب المريد','الشيخ والمريد','التوبة والإنابة','الصدق والإخلاص','محبة الله','الرضا بالقضاء','الأعيان الثابتة','النفس الأمارة','حسن الخلق']
 bare=[]
 for q in phrases:
  result_cache.clear();t=time.perf_counter();r=search_library(query=q,limit=5);bare.append({'query':q,'seconds':round(time.perf_counter()-t,6),'ok':not r.get('error'),'mode':r.get('effective_match_mode'),'request_id':r.get('request_id')})
 cold=[r['seconds'] for r in runs if r['state']=='response_cache_cold'];warm=[r['seconds'] for r in runs if r['state']=='warm']
 byfamily={}
 for family in sorted({r['id'][0] for r in runs}):
  rows=[r for r in runs if r['id'][0]==family];byfamily[family]={'calls':len(rows),'completion':sum(r['ok'] for r in rows)/len(rows)}
 result_cache.clear();r=search_library(query='طمأنينة',match_mode='lexeme',include_counts=True,limit=5)
 summary={'scope':'Local direct tool calls, response-cache cold is not OS-cache cold. First process call included; deployment acceptance pending.',
 'calls':len(runs),'completion_rate':sum(r['ok'] for r in runs)/len(runs),'cold_p50_seconds':statistics.median(cold),'cold_p95_seconds':percentile(cold),'cold_max_seconds':max(cold),'warm_p95_seconds':percentile(warm),'warm_max_seconds':max(warm),'bare_phrase_p95_seconds':percentile([r['seconds'] for r in bare]),'bare_phrase_errors':sum(not r['ok'] for r in bare),'families':byfamily,'census':{k:r.get(k) for k in ['literal_matching_pages','retrieval_hit_count','retrieval_completeness','timing']},'ids_bytes':len(json.dumps(list_books(projection='ids',book_ids=['b14','b41']),ensure_ascii=False).encode())}
 (ROOT/'verification/2.10.0/acceptance.json').write_text(json.dumps({'summary':summary,'calls':runs,'bare_phrases':bare},ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
