#!/usr/bin/env python3
"""Public development replay. Reference presence is not answer accuracy."""
import sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from app.mcp_server import search_library
NEW=['ما آداب المريد مع شيخه','ما فضل الصلاة على النبي صلى الله عليه وسلم','كيف يتوب العبد من ذنوبه وهل يقبل الله توبته','كيف يتخلص المريد من الكبر والعجب بالنفس','ما حكم زيارة قبور الأولياء والتوسل بهم','إزاي أربي ولادي تربية صالحة','ما معنى الفناء والبقاء في طريق القوم','ما هي الحقيقة المحمدية','ما فضل ليلة القدر وكيف نحييها','إيه رأي مولانا في الاحتفال بالمولد النبوي','كيف يبر الإنسان والديه بعد موتهما']
old=json.loads((ROOT/'tests/data/audit_270_regressions.json').read_text())['suite'];items=[{**q,'set':'known30'} for q in old]+[{'id':f'new{i+1}','query':q,'args':{'query':q,'limit':5,'context_chars':180},'reference_pages':[],'set':'public11'} for i,q in enumerate(NEW)];results=[]
for q in items:
 start=time.monotonic();r=search_library(**q['args']);ids=[f"{h['book_id']}:{h['seq']}" for h in r.get('results',[])];found=bool(set(ids)&set(q['reference_pages'])) if q['reference_pages'] else None;out={**q,'seconds':round(time.monotonic()-start,3),'result_ids':ids,'reference_found':found,'response':r};results.append(out);print(q['id'],out['seconds'],ids,found,flush=True)
summary={'scope':'public development fixtures, not held-out or independently graded','known30_nonempty':sum(bool(q['result_ids']) for q in results if q['set']=='known30'),'known30_reference_presence':sum(q['reference_found'] is True for q in results if q['set']=='known30'),'public11_nonempty':sum(bool(q['result_ids']) for q in results if q['set']=='public11'),'errors':sum(bool(q['response'].get('error')) for q in results)}
(ROOT/'verification/2.10.0/public_replay.json').write_text(json.dumps({'summary':summary,'questions':results},ensure_ascii=False,indent=2));print(json.dumps(summary))
