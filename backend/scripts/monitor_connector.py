#!/usr/bin/env python3
"""Scheduled mixed HTTP samples. Exit nonzero above 1% failure."""
import argparse,asyncio,json,time,os
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
CASES=[('list_books',{'projection':'ids'}),('get_book',{'book_id':'b07'}),('get_page',{'book_id':'b07','seq':166,'max_chars':200}),('get_passage',{'match_id':'b07-p166-c1180','context_chars':200})]+[('search_library',{'query':q,'limit':5}) for q in ['من ضاقت عليه المعيشة كيف ينال سعة الرزق','ماذا يفعل من ضاق رزقه واشتدت حاجته','كيف يتعامل المريد مع الحزن وضيق الصدر','ما النصيحة لمن يشعر بالهم والحزن','ما فضل الصلاة على النبي صلى الله عليه وسلم','ما هي الحقيقة المحمدية']]
async def run(url,count=20):
 results=[];headers={'Authorization':'Bearer '+os.environ['MCP_MONITOR_API_KEY']} if os.environ.get('MCP_MONITOR_API_KEY') else None
 async with streamablehttp_client(url,headers=headers,httpx_client_factory=lambda **kw:httpx.AsyncClient(**{**kw,'timeout':25,'trust_env':False})) as (read,write,_):
  async with ClientSession(read,write) as session:
   await session.initialize()
   for i in range(count):
    name,args=CASES[i%len(CASES)];start=time.monotonic()
    try:
     r=await session.call_tool(name,args);data=r.structuredContent
     if not data and r.content:
      try:data=json.loads(r.content[0].text)
      except ValueError:data={'error':str(r.content[0].text)[:500]}
     data=data if isinstance(data,dict) else {}
     complete=name!='search_library' or data.get('completion')=='full'
     ok=not r.isError and bool(data) and not data.get('error') and complete
     error=None if ok else ({'error':{'code':'partial_completion','message':'Search skipped a planned stage'}} if not complete and not data.get('error') else data)
    except Exception as exc:ok=False;error=type(exc).__name__
    results.append({'tool':name,'ok':ok,'ms':round((time.monotonic()-start)*1000,3),'error':error,'request_id':data.get('request_id') if isinstance(locals().get('data'),dict) else None})
    if (i+1)%20==0:print(f'{i+1}/{count} completed',flush=True)
 times=sorted(r['ms'] for r in results);questions=sorted(r['ms'] for r in results if r['tool']=='search_library')
 return {'timestamp':time.time(),'endpoint':url,'calls':count,'successful':sum(r['ok'] for r in results),'p95_ms':times[min(len(times)-1,int(len(times)*.95))],'question_p95_ms':questions[min(len(questions)-1,int(len(questions)*.95))] if questions else None,'results':results}
def main():
 p=argparse.ArgumentParser();p.add_argument('url');p.add_argument('--count',type=int,default=20);p.add_argument('--output',default='monitor-result.json');p.add_argument('--history');a=p.parse_args();report=asyncio.run(run(a.url,a.count));Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2))
 if a.history:
  history=Path(a.history);old=json.loads(history.read_text()) if history.exists() else [];old=[r for r in old if r['timestamp']>time.time()-7*86400];old.append(report);history.write_text(json.dumps(old))
 print(json.dumps({k:v for k,v in report.items() if k!='results'}));return int(1-report['successful']/report['calls']>.01)
if __name__=='__main__':raise SystemExit(main())
