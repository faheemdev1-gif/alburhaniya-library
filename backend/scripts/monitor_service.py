#!/usr/bin/env python3
"""Supervised fixed-question probes. History contains measured data only."""
import asyncio,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from scripts.monitor_connector import run

def main():
 parent=os.getppid();port=int(os.environ.get('PORT','8000'))
 from app.core.config import get_settings
 settings=get_settings();history=Path(settings.monitor_summary_path)
 from app.mcp_contract import SERVER_VERSION
 history.parent.mkdir(parents=True,exist_ok=True)
 try: old=json.loads(history.read_text()) if history.exists() else []
 except (OSError,ValueError):old=[]
 old=old if isinstance(old,list) else [old]
 old=[r for r in old if r.get('timestamp',0)>time.time()-7*86400]
 old.append({'event':'restart','timestamp':time.time(),'server_version':SERVER_VERSION})
 tmp=history.with_suffix('.tmp');tmp.write_text(json.dumps(old));tmp.replace(history)
 keys=[k.strip() for k in settings.mcp_api_keys.split(',') if k.strip()]
 if keys:os.environ.setdefault('MCP_MONITOR_API_KEY',keys[0])
 next_probe=time.monotonic()+15
 while os.getppid()==parent:
  if time.monotonic()<next_probe:time.sleep(min(5,next_probe-time.monotonic()));continue
  try:
   report=asyncio.run(run(f'http://127.0.0.1:{port}/mcp/',10))
   old=json.loads(history.read_text()) if history.exists() else []
   old=[r for r in old if r.get('timestamp',0)>time.time()-7*86400];old.append(report)
   history.parent.mkdir(parents=True,exist_ok=True);tmp=history.with_suffix('.tmp');tmp.write_text(json.dumps(old));tmp.replace(history)
  except Exception as exc:
   print('Monitoring probe failed: '+type(exc).__name__,file=sys.stderr,flush=True)
  next_probe=time.monotonic()+300
if __name__=='__main__':main()
