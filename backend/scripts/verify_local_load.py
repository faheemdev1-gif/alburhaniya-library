#!/usr/bin/env python3
"""Two-worker production launcher; real local HTTP sample, not deployed proof."""
import asyncio,json,os,socket,subprocess,sys,time
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT));os.chdir(ROOT)
from scripts.monitor_connector import run
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
with (ROOT/'verification/2.9.0/load_server.log').open('w') as log:
 server=subprocess.Popen([sys.executable,'scripts/start_server.py'],env={**os.environ,'PORT':str(port),'WEB_CONCURRENCY':'2'},stdout=log,stderr=log)
 try:
  with httpx.Client(trust_env=False) as client:
   for _ in range(150):
    try:
     if client.get(f'http://127.0.0.1:{port}/health',timeout=1).status_code==200:break
    except httpx.HTTPError:pass
    time.sleep(.1)
   else:raise RuntimeError('Readiness timeout')
  report=asyncio.run(run(f'http://127.0.0.1:{port}/mcp/',500));report['scope']='local two-worker HTTP, not deployed reliability or 24-hour monitoring';(ROOT/'verification/2.9.0/local_500_calls.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='results'}))
 finally:
  server.terminate()
  try:server.wait(timeout=10)
  except subprocess.TimeoutExpired:server.kill();server.wait()
