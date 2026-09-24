#!/usr/bin/env python3
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from app.mcp_server import get_passage
out=[]
for n in range(1,96):
 result=get_passage(qasida_number=n);bayts=result.get('bayts',[]);nums=[b['bayt_number'] for b in bayts];ok=bool(bayts) and nums==list(range(1,len(bayts)+1)) and all(b['stable_id']==f'b14-q{n:03}-b{b["bayt_number"]:03}' for b in bayts);out.append({'qasida':n,'bayts':len(bayts),'ok':ok})
report={'qasidas':len(out),'passed':sum(r['ok'] for r in out),'bayts':sum(r['bayts'] for r in out),'results':out};(ROOT/'verification/2.9.0/diwan_sweep.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='results'}));raise SystemExit(0 if report['passed']==95 and report['bayts']==2682 else 1)
