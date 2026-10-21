#!/usr/bin/env python3
"""Reproducible local hosting + real MCP SDK verification, never deployment."""
import asyncio,json,math,os,signal,socket,subprocess,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from scripts.production_mcp_regression import run,_structured
from app.services.compact_response import decode_search_response
from app.mcp_contract import SERVER_VERSION

async def probe(endpoint,query):
 started=time.perf_counter()
 async with httpx.AsyncClient(timeout=30,trust_env=False) as client, streamable_http_client(endpoint,http_client=client) as (read,write,_):
  async with ClientSession(read,write) as session:
   await session.initialize()
   result=_structured(await session.call_tool('search_library',{'query':query,'limit':5}))
 return {'ms':round((time.perf_counter()-started)*1000,3),'error':result.get('error'),
         'returned_count':len(result.get('results',[])),'completion':result.get('completion')}

async def verify(base):
 async with httpx.AsyncClient(trust_env=False) as client:
  for _ in range(200):
   try:
    response=await client.get(base+'/health',timeout=1)
    if response.status_code==200:break
   except httpx.HTTPError:pass
   await asyncio.sleep(.1)
  else:raise RuntimeError('Local server did not become healthy')
 endpoint=base+'/mcp/'
 smoke=await run(endpoint)
 queries=['ما أهمية الخلوة للسالك','ماذا ينال من يحب سيدنا محمد',
          'ما علامات المريد الصادق','كيف يجمع السالك بين خشية الله والأمل في عفوه',
          'كيف يكون اتصال المريد بالمشايخ بالفواتح','ما شروط التوبة حتى لا تكون مجرد كلام باللسان',
          'إذا تركت وردي مدة فهل أعود للاسم الذي كنت فيه','هل البيع والشراء يمنعان العبد من ذكر الله بقلبه']
 concurrent=await asyncio.gather(*(probe(endpoint,q) for q in queries))
 assert not any(x['error'] or not x['returned_count'] for x in concurrent)
 # Exercise both new representations over the SDK, using the server cache.
 async with httpx.AsyncClient(timeout=30,trust_env=False) as client, streamable_http_client(endpoint,http_client=client) as (read,write,_):
  async with ClientSession(read,write) as session:
   await session.initialize();outputs=[]
   for mode in ('compact','ultra_compact'):
    outputs.append(_structured(await session.call_tool('search_library',{'query':'الله','qasida_number':91,'match_mode':'exact','limit':5,'expand_top':2,'mode':mode})))
   assert decode_search_response(outputs[0])==decode_search_response(outputs[1])
 return {'version':SERVER_VERSION,'scope':'local two-worker HTTP host and actual MCP SDK; cache reuse allowed; not production evidence',
         'smoke':smoke,'concurrent':concurrent,'concurrent_errors':0,'sdk_minimal_equivalence':'pass',
         'concurrent_client_max_ms':max(x['ms'] for x in concurrent)}

def main():
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 dest=ROOT/'verification'/SERVER_VERSION;dest.mkdir(parents=True,exist_ok=True)
 env={**os.environ,'PORT':str(port),'WEB_CONCURRENCY':'2','MONITOR_ENABLED':'false',
      'MCP_API_KEYS':'','MCP_REQUESTS_PER_MINUTE':'10000','RESULT_CACHE_PATH':'/tmp/alburhaniya-http-validation-16-'+uuid.uuid4().hex+'.sqlite3'}
 with (dest/'http_server.log').open('w') as log:
  process=subprocess.Popen([sys.executable,'scripts/start_server.py'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  try:report=asyncio.run(verify('http://127.0.0.1:'+str(port)))
  finally:
   os.killpg(process.pid,signal.SIGTERM)
   try:process.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
 (dest/'http_mcp_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'smoke_checks':len(report['smoke']['smoke']),'concurrent_errors':0,
   'sdk_minimal_equivalence':report['sdk_minimal_equivalence'],'concurrent_client_max_ms':report['concurrent_client_max_ms']},indent=2))
if __name__=='__main__':main()
