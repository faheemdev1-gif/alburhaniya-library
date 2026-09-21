#!/usr/bin/env python3
"""Replay the supplied development audit; do not claim held-out accuracy."""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from app.mcp_server import search_library,get_page,get_passage,list_books

def main():
 suite=json.loads((ROOT/'tests/data/audit_270_regressions.json').read_text())['suite'];out=[]
 for q in suite:
  start=time.perf_counter();r=search_library(**q['args']);elapsed=time.perf_counter()-start
  hits=r.get('results',[])
  ids=[f"{h['book_id']}:{h['seq']}" for h in hits]
  reference=bool(set(ids)&set(q['reference_pages']))
  out.append(dict(id=q['id'],query=q['query'],reference_pages=q['reference_pages'],reference_found=reference,seconds=elapsed,response=r))
  print(q['id'],round(elapsed,3),ids,'reference',reference,flush=True)
 (ROOT/'verification/audit_replay_280.json').write_text(json.dumps({'scope':'known audit regressions; reference presence is not direct-support accuracy','questions':out},ensure_ascii=False,indent=2)+'\n')
 print('reference presence',sum(q['reference_found'] for q in out), '/',len(out))
if __name__=='__main__':main()
