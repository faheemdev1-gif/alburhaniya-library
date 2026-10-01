#!/usr/bin/env python3
"""Real local HTTP load at 1/2/4/8 clients; keeps every first attempt."""
import asyncio,json,os,socket,subprocess,sys,time,math
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT));os.chdir(ROOT)
QUERIES=['من ضاقت عليه المعيشة كيف ينال سعة الرزق','ماذا يفعل من ضاق رزقه واشتدت حاجته','كيف يتعامل المريد مع الحزن وضيق الصدر','ما النصيحة لمن يشعر بالهم والحزن','ما فضل الصلاة على النبي صلى الله عليه وسلم','هل قراءة الأوراد تغني عن العمل لطلب الرزق','كيف أحافظ على الصلاة في وقتها','كيف أداوم على تلاوة القرآن كل يوم']
async def batch(url,concurrency):
 sem=asyncio.Semaphore(concurrency)
 async def one(i):
  async with sem:
   async with streamablehttp_client(url,httpx_client_factory=lambda **kw:httpx.AsyncClient(**{**kw,'timeout':30,'trust_env':False})) as (read,write,_):
    async with ClientSession(read,write) as session:
     await session.initialize();t=time.perf_counter()
     r=await session.call_tool('search_library',{'query':QUERIES[i%len(QUERIES)],'limit':5,'context_chars':180+concurrency*20+i})
     d=r.structuredContent or json.loads(r.content[0].text)
     return {'i':i,'seconds':time.perf_counter()-t,'ok':not r.isError and not d.get('error'),'completion':d.get('completion'),'nonempty':bool(d.get('results')),'timing':d.get('timing'),'request_id':d.get('request_id'),'error':d.get('error'),'cache':d.get('cache')}
 return await asyncio.gather(*(one(i) for i in range(16)))
async def parity(url):
 async with streamablehttp_client(url,httpx_client_factory=lambda **kw:httpx.AsyncClient(**{**kw,'timeout':30,'trust_env':False})) as (read,write,_):
  async with ClientSession(read,write) as session:
   await session.initialize();listed=await session.list_tools();schemas={t.name:t.inputSchema for t in listed.tools};checks=[]
   probes=[('search_library',{'query':'الحقيقة المحمدية','check_completeness':True,'include_toc':True,'include_topic_only':True,'detail':'full','keep_terms':['الحقيقة']}),('get_passage',{'match_id':'b07-p166-c1180','context_mode':'paragraph','max_chars':500}),('list_books',{'projection':'ids','book_ids':['b14','b41']})]
   for name,args in probes:
    r=await session.call_tool(name,args);d=r.structuredContent or json.loads(r.content[0].text);checks.append({'tool':name,'parameters':list(args),'ok':not r.isError and not d.get('error'),'request_id':d.get('request_id')})
   return {'scope':'fresh local MCP SDK client; ChatGPT/Claude client refresh unverified','schemas':schemas,'calls':checks}
def main():
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 rows=[]
 with (ROOT/'verification/2.10.0/load_server.log').open('w') as log:
  server=subprocess.Popen([sys.executable,'scripts/start_server.py'],env={**os.environ,'PORT':str(port),'WEB_CONCURRENCY':'2','MONITOR_ENABLED':'false'},stdout=log,stderr=log)
  try:
   with httpx.Client(trust_env=False) as c:
    for _ in range(150):
     try:
      if c.get(f'http://127.0.0.1:{port}/health',timeout=1).status_code==200:break
     except httpx.HTTPError:pass
     time.sleep(.1)
    else:raise RuntimeError('Server not ready')
   url=f'http://127.0.0.1:{port}/mcp/'
   for n in [1,2,4,8]:
    samples=asyncio.run(batch(url,n));times=sorted(s['seconds'] for s in samples);row={'clients':n,'calls':len(samples),'completion':sum(s['ok'] for s in samples)/len(samples),'full_rate':sum(s['completion']=='full' for s in samples)/len(samples),'p95_seconds':times[math.ceil(len(times)*.95)-1],'max_seconds':max(times),'samples':samples};rows.append(row);print(json.dumps({k:v for k,v in row.items() if k!='samples'}),flush=True)
   report={'scope':'Local HTTP, two workers, response cache misses via distinct excerpt controls. Network/deployed hardware not tested.','runs':rows,'client_parity':asyncio.run(parity(url))}
   (ROOT/'verification/2.10.0/load.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
  finally:
   server.terminate()
   try:server.wait(timeout=10)
   except subprocess.TimeoutExpired:server.kill();server.wait()
if __name__=='__main__':main()
