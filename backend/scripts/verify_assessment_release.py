#!/usr/bin/env python3
"""Fixed-source inclusion gates and repeatable local MCP query measurements."""
import argparse
import json
import math
import os
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
from app.services import library_db as db
from app.mcp_server import search_library, get_passage, mcp
from app.mcp_contract import TOOL_META, bind_callable_schema

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--output', default='verification.json')
    args = parser.parse_args()
    cases = json.loads((ROOT/'tests/data/assessment_literal_cases.json').read_text())['cases']
    results = []
    for case in cases:
        query, scope = case['query'], {'book_ids':case['book_ids']}
        expected = set(case['expected_literal_pages'])
        exact = db._matching_page_ids([query], **scope)
        lexeme = db._matching_page_ids([query], search_mode='lexeme', **scope)
        exact = {f'{b}-p{s}' for b,s in exact}
        lexeme = {f'{b}-p{s}' for b,s in lexeme}
        count = db.search_stats([query], **scope)['matching_occurrences']
        passed = exact == expected and expected <= lexeme and count == case['expected_literal_occurrences']
        results.append({'query':query,'split':case['split'],'passed':passed,
                        'literal_pages':len(expected),'missing':sorted(expected-lexeme),
                        'exact_symmetric_difference':sorted(expected ^ exact),
                        'expected_occurrences':case['expected_literal_occurrences'],'actual_occurrences':count})
    bind_callable_schema(mcp)
    conflict = search_library(query='طمأنينة', match_mode='exact', search_mode='lexeme')
    assert conflict['error']['code'] == 'invalid_request'
    alias = search_library(query='طمأنينة', search_mode='lexeme', limit=3)
    assert alias['effective_match_mode'] == 'lexeme'
    assert alias['contract']['tool_contract_version'] == TOOL_META['tool_contract_version']
    context = get_passage(match_id=alias['results'][0]['match_id'], context_mode='paragraph')
    assert 'context_segments' in context and 'complete_paragraph' in context
    benchmarks = []
    for query, mode in [('طمأنينة','lexeme'),('المحافظة على الصلاة وعدم تأخيرها عن وقتها','auto'),('من ضاقت عليه المعيشة كيف ينال سعة الرزق','auto')]:
        runs=[]
        for _ in range(max(1,args.runs)):
            started=time.perf_counter()
            result=search_library(query=query,match_mode=mode,include_counts=True,limit=5)
            runs.append({'elapsed_ms':round((time.perf_counter()-started)*1000,2),
                         'error':result.get('error'),'returned':len(result.get('results',[])),
                         'bytes':len(json.dumps(result,ensure_ascii=False).encode()),
                         'timing':result.get('timing')})
        times=sorted(r['elapsed_ms'] for r in runs)
        benchmarks.append({'query':query,'match_mode':mode,'p50_ms':times[math.ceil(.5*len(times))-1],
            'p95_ms':times[math.ceil(.95*len(times))-1],'errors':sum(bool(r['error']) for r in runs),'runs':runs})
    report={'contract':TOOL_META,'fixture_cases':results,'all_passed':all(r['passed'] for r in results),
            'benchmark_environment':'local Python calls; includes first measured call; excludes HTTP network and production load',
            'benchmarks':benchmarks,'semantic_index_tested':False}
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'fixture_passed':sum(r['passed'] for r in results),'fixture_total':len(results),
                      'benchmarks':[{k:v for k,v in b.items() if k!='runs'} for b in benchmarks]},ensure_ascii=False))
    raise SystemExit(0 if report['all_passed'] and not any(b['errors'] for b in benchmarks) else 1)
if __name__=='__main__': main()
