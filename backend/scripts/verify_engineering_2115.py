#!/usr/bin/env python3
"""Replay disclosed PDF fixtures. Page presence is not Direct@5 grading."""
import json,time,sys,math,hashlib,logging
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from app.mcp_server import search_library,get_passage
from app.services.compact_response import decode_search_response
from app.core import result_cache
from app.mcp_contract import SERVER_VERSION
logging.getLogger('app.services.traffic_metrics').setLevel(logging.WARNING)
def main():
    cases=json.loads((ROOT/'tests/data/engineering_spec_fixtures_2115.json').read_text())['fixtures']
    result_cache.clear();out=[]
    for f in cases:
        args=f['recorded_arguments'].copy()
        if f['recorded_tool']=='search_library':args['detail']='full'
        t=time.perf_counter();r={'search_library':search_library,'get_passage':get_passage}[f['recorded_tool']](**args)
        expected=f['proposed_expected_outcome'];hints=expected.get('source_pages_any')
        returned={f"{h['book_id']}-p{h['seq']}" for h in r.get('results',[])}
        out.append({'id':f['fixture_id'],'query':args.get('query'),'ms':round((time.perf_counter()-t)*1000,3),
                    'source_page_in_top5':bool(returned&set(hints)) if hints else None,
                    'expected':expected,'arguments':args,'response':r})
    scoped=[r for r in out if r['source_page_in_top5'] is not None]
    times=sorted(r['ms'] for r in out)
    report={'version':SERVER_VERSION,'scope':'28 disclosed PDF development fixtures; local sequential first attempts after cache clear; no independent answer grading',
      'summary':{'calls':len(out),'errors':sum(bool(r['response'].get('error')) for r in out),
        'source_page_in_top5_numerator':sum(r['source_page_in_top5'] for r in scoped),'source_page_in_top5_denominator':len(scoped),
        'local_p50_ms':times[len(times)//2],'local_p95_ms':times[math.ceil(.95*len(times))-1],
        'quality_score':None,'quality_score_reason':'Requires independently owned and graded held-out families and production observation'},'cases':out}
    dest=ROOT/'verification'/SERVER_VERSION/'engineering_replay.json';dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report['summary'],indent=2))
if __name__=='__main__':main()
