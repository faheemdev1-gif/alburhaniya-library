#!/usr/bin/env python3
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from app.mcp_server import mcp
from app.mcp_contract import contract_metadata
(ROOT/'docs').mkdir(exist_ok=True)
(ROOT/'docs/tool-schemas.json').write_text(json.dumps({'contract':contract_metadata(),'tools':[{'name':t.name,'description':t.description,'inputSchema':t.parameters} for t in mcp._tool_manager.list_tools()]},ensure_ascii=False,indent=2)+'\n')
print('Exported all five callable schemas')
