#!/usr/bin/env python3
"""Compare formatting on frozen original 2.8 payloads with identical evidence."""
import sys,json,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
import tiktoken
from app.services.compact_response import slim_response
enc=tiktoken.get_encoding('cl100k_base');fixtures=json.loads((ROOT/'tests/data/payload_280_frozen.json').read_text())['fixtures'];results=[]
for item in fixtures:
 original=item['payload'];ultra=item['mode']=='ultra_compact';after=slim_response(copy.deepcopy(original),ultra=ultra);keys=('m','x','c') if ultra else ('match_id','excerpt','citation_label')
 assert [[h.get(k) for k in keys] for h in original['results']]==[[h.get(k) for k in keys] for h in after['results']]
 before_text=json.dumps(original,ensure_ascii=False,separators=(',',':'));after_text=json.dumps(after,ensure_ascii=False,separators=(',',':'))
 results.append({'fixture':item['fixture'],'mode':item['mode'],'hits':len(original['results']),'same_citations_and_excerpts':True,'before_chars':len(before_text),'after_chars':len(after_text),'character_reduction_pct':round(100*(1-len(after_text)/len(before_text)),2),'before_bytes':len(before_text.encode()),'after_bytes':len(after_text.encode()),'before_tokens':len(enc.encode(before_text)),'after_tokens':len(enc.encode(after_text))})
report={'scope':'Formatter-only transformation of frozen original 2.8 payloads. Identical citations and excerpts. Excludes common transport/contract envelope; not an end-to-end ranking comparison or independently verified answer cost.','baseline_fixture':'tests/data/payload_280_frozen.json','tokenizer':'cl100k_base','calls_for_search_and_one_bounded_followup':2,'results':results}
(ROOT/'verification/2.10.0/payload_measurements.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
