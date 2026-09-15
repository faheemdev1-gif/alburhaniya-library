#!/usr/bin/env python3
"""Reproducible local evidence: real MCP client, timings, tokens and corpus gates.

Never presents local timings as production SLA measurements or token counts as
an invoice. CPU/OS caches are uncontrolled; first-request and warm timings are
reported separately. Each MCP scenario starts a fresh server process.
"""
import argparse
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import time
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
os.chdir(ROOT)
from app.services import library_db as db
from app.mcp_contract import SERVER_VERSION, TOOL_META, REQUIRED_TOOLS
from scripts.independent_corpus_audit import audit
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def summary(values):
    ordered=sorted(values)
    return {'p50_ms':round(statistics.median(values),2),
            'p95_ms':round(ordered[math.ceil(.95*len(values))-1],2),
            'samples':len(values)}


def direct_benchmarks(runs):
    baseline=json.loads((ROOT/'verification/baseline_260.json').read_text())
    cases=[('lexeme',lambda:db.search('طمأنينة',search_mode='lexeme',limit=5)),
           ('multi_lexeme',lambda:db.search(queries=['إيمان','مسألة'],search_mode='lexeme',limit=5)),
           ('prayer_hybrid',lambda:db.hybrid_search(query='المحافظة على الصلاة وعدم تأخيرها عن وقتها',limit=5)),
           ('livelihood_hybrid',lambda:db.hybrid_search(query='من ضاقت عليه المعيشة كيف ينال سعة الرزق',limit=5))]
    out=[]
    for (name,fn),old in zip(cases,baseline['cases']):
        times=[]
        for _ in range(runs):
            t=time.perf_counter();result=fn();times.append((time.perf_counter()-t)*1000)
        ids=[r['match_id'] for r in result]
        out.append({'name':name,'ms':[round(t,2) for t in times],**summary(times),
            'first_request_ms':round(times[0],2),'warm':summary(times[1:]),
            'baseline_median_ms':old['median_ms'],
            'median_change_percent':round((statistics.median(times)/old['median_ms']-1)*100,2),
            'result_ids':ids,'unchanged_result_ids':ids==old['result_ids']})
        if ids!=old['result_ids']:raise AssertionError(f'Baseline evidence changed for {name}')
    return out


def structured(result):
    if result.isError:raise AssertionError(str(result.content))
    value=result.structuredContent
    if value is None:
        value=json.loads(next(c.text for c in result.content if c.type=='text'))
    if value.get('error'):raise AssertionError(value['error'])
    return value


async def transport_checks(runs):
    import tiktoken
    encoder=tiktoken.get_encoding('cl100k_base')
    scenarios=[('lexeme','search_library',{'query':'طمأنينة','match_mode':'lexeme','include_counts':True,'limit':5}),
               ('multi_lexeme','search_library',{'queries':['إيمان','مسألة'],'match_mode':'lexeme','check_completeness':True,'limit':5}),
               ('livelihood','search_library',{'query':'من ضاقت عليه المعيشة كيف ينال سعة الرزق','limit':5}),
               ('paragraph','get_passage',{'match_id':'b11-p132-c304','context_mode':'paragraph','max_chars':3000}),
               ('catalogue_ids','list_books',{'projection':'ids'})]
    out=[]
    params=StdioServerParameters(command=sys.executable,args=[str(ROOT/'scripts/serve_stdio.py')],cwd=str(ROOT))
    with (ROOT/'verification/mcp_server.log').open('w') as log:
        for name,tool,args in scenarios:
            async with stdio_client(params,errlog=log) as (read,write):
                async with ClientSession(read,write) as session:
                    init=await session.initialize()
                    listed=await session.list_tools()
                    assert {t.name for t in listed.tools}==REQUIRED_TOOLS
                    assert init.serverInfo.version==SERVER_VERSION
                    props={t.name:t.inputSchema['properties'] for t in listed.tools}
                    assert 'context_mode' in props['get_passage']
                    assert 'check_completeness' in props['search_library']
                    assert 'projection' in props['list_books']
                    samples=[]
                    for _ in range(runs):
                        start=time.perf_counter()
                        response=await session.call_tool(tool,args)
                        elapsed=(time.perf_counter()-start)*1000
                        value=structured(response)
                        serialized=json.dumps(value,ensure_ascii=False,separators=(',',':'))
                        wire=response.model_dump_json(exclude_none=True)
                        samples.append({'client_ms':round(elapsed,2),
                            'server_ms':value['timing']['total_ms'],'attempts':value['timing']['attempts'],
                            'phases_ms':value['timing']['phases_ms'],
                            'structured_tokens':len(encoder.encode(serialized)),
                            'complete_mcp_result_tokens':len(encoder.encode(wire)),
                            'request_id':value['request_id']})
                        if name in ('lexeme','multi_lexeme'):
                            assert value['retrieval_completeness']['status']=='ok'
                        if name=='paragraph':
                            assert value['cross_page'] and value['context_segments']
                    out.append({'scenario':name,'tool':tool,'args':args,'fresh_tools_list':True,
                        'first_request':samples[0],
                        'warm_client':summary([s['client_ms'] for s in samples[1:]]),
                        'warm_server':summary([s['server_ms'] for s in samples[1:]]),
                        'samples':samples})
        # Cost of a concrete verified-evidence workflow, including the expansion.
        async with stdio_client(params,errlog=log) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                catalogue_cost={}
                for projection in ('compact','ids','full'):
                    r=structured(await session.call_tool('list_books',{'projection':projection}))
                    catalogue_cost[projection]=len(encoder.encode(json.dumps(r,ensure_ascii=False,separators=(',',':'))))
                workflow={}
                for mode in ('compact','ultra_compact'):
                    response=await session.call_tool('search_library',{'query':'طمأنينة','match_mode':'lexeme','mode':mode,'limit':6})
                    r=structured(response)
                    hit=r['results'][0]
                    passage=structured(await session.call_tool('get_passage',{'match_id':hit.get('match_id',hit.get('m')),'context_mode':'paragraph'}))
                    assert passage.get('citation_label')
                    workflow[mode]={'tool_calls':2,'structured_tokens':sum(len(encoder.encode(json.dumps(x,ensure_ascii=False,separators=(',',':')))) for x in (r,passage)),
                                    'evidence_check':'literal hit expanded with a valid citation; not a reviewed answer-quality score'}
    return {'transport':'local MCP stdio with fresh subprocess per scenario; excludes HTTP/network/deployment latency',
            'tokenizer':'cl100k_base; descriptive token counts, not actual client context usage or billing',
            'cases':out,'catalogue_structured_tokens':catalogue_cost,'evidence_workflow':workflow}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--runs',type=int,default=7)
    parser.add_argument('--output',default='verification/release_270.json')
    args=parser.parse_args();runs=max(3,args.runs)
    (ROOT/'verification').mkdir(exist_ok=True)
    corpus=audit(ROOT/'library.db')
    assert corpus['status']=='pass'
    result={'server_version':SERVER_VERSION,'environment':{'python':platform.python_version(),
            'platform':platform.platform(),'production_tested':False,'os_caches_controlled':False},
            'corpus_audit':corpus,'direct_benchmarks':direct_benchmarks(runs),
            'mcp':asyncio.run(transport_checks(runs)),
            'external_score':None,'human_relevance_review':'pending','documentary_provenance_review':'pending'}
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'pass','output':args.output,
        'benchmarks':[{k:v for k,v in c.items() if k in ('name','p50_ms','baseline_median_ms','median_change_percent','unchanged_result_ids')} for c in result['direct_benchmarks']],
        'catalogue_tokens':result['mcp']['catalogue_structured_tokens']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
