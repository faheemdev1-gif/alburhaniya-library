#!/usr/bin/env python3
"""Capture first local attempts for all disclosed public report wordings.

This script records retrieval behavior, not human answer grades. It does not
turn a development suite into a private or blind quality score.
"""
import json
import math
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from app.core import result_cache
from app.mcp_contract import SERVER_VERSION
from app.mcp_server import search_library


def main():
    cases=json.loads((ROOT/'tests/data/public_wordings_2111.json').read_text())
    result_cache.clear()
    rows=[]
    for c in cases:
        started=time.perf_counter()
        result=search_library(query=c['query'],limit=5,detail='full')
        rows.append({'id':c['id'],'query':c['query'],
                     'local_ms':round((time.perf_counter()-started)*1000,2),
                     'completion':result.get('completion'),
                     'evidence_strength':result.get('evidence_strength'),
                     'unresolved_facets':result.get('unresolved_facets',[]),
                     'reformulation_status':result.get('reformulation_status'),
                     'error':result.get('error'),
                     'hits':[{'book_id':h['book_id'],'seq':h['seq'],
                              'relevance':h.get('question_relevance'),
                              'match_id':h.get('match_id')}
                             for h in result.get('results',[])]})
    timings=sorted(r['local_ms'] for r in rows)
    output={'server_version':SERVER_VERSION,
            'scope':'31 disclosed public wordings, local first attempt after cache clear; no answer grading',
            'summary':{'queries':len(rows),'errors':sum(bool(r['error']) for r in rows),
                       'full':sum(r['completion']=='full' for r in rows),
                       'weak':sum(r['evidence_strength']=='weak' for r in rows),
                       'partial_evidence':sum(r['evidence_strength']=='partial' for r in rows),
                       'local_p95_ms':timings[math.ceil(.95*len(rows))-1]},
            'cases':rows}
    path=ROOT/'verification'/SERVER_VERSION/'public_replay.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(output['summary'],ensure_ascii=False))


if __name__=='__main__':main()
