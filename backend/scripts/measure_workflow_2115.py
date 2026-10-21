#!/usr/bin/env python3
"""Evidence-equivalent projection costs with pinned public encoding profiles.

These are local payload costs, not proprietary Claude tokenizer counts or
production billed-model usage. Full tool schemas and follow-up context are
included, with actual evidence equivalence checked before comparison.
"""
import json,sys,logging,importlib.metadata
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
import tiktoken
from app.mcp_server import search_library,get_passage,mcp
from app.core import result_cache
from app.mcp_contract import SERVER_VERSION
from app.services.compact_response import decode_search_response
logging.getLogger('app.services.traffic_metrics').setLevel(logging.WARNING)
def packed(v):return json.dumps(v,ensure_ascii=False,separators=(',',':'))
def main():
    encodings={name:tiktoken.get_encoding(name) for name in ['cl100k_base','o200k_base']}
    schemas=[{'name':t.name,'description':t.description,'inputSchema':t.parameters} for t in mcp._tool_manager.list_tools()]
    fixtures=[('one_hit_question',{'query':'ما علامات المريد الصادق','limit':1,'context_chars':40}),
      ('five_hit_conjunction',{'queries':['الخلوة','المراقبة'],'match_mode':'terms','operator':'AND','limit':6}),
      ('six_hit_lexical',{'queries':['الخلوة','المراقبة'],'match_mode':'terms','operator':'OR','limit':6}),
      ('census',{'query':'التوبة','match_mode':'exact','include_counts':True,'limit':5}),
      ('weak_negative',{'query':'ما حكم استعمال الهاتف في الصلاة','limit':5})]
    results=[]
    for label,args in fixtures:
        payloads={}
        for mode in ['compact','ultra_compact']:
            result_cache.clear();payloads[mode]=search_library(**args,mode=mode)
        assert decode_search_response(payloads['compact'])==decode_search_response(payloads['ultra_compact'])
        hits=decode_search_response(payloads['compact'])['results']
        if label=='six_hit_lexical':assert len(hits)==6
        follow=get_passage(match_id=hits[0]['match_id'],context_chars=300) if hits else {}
        for profile,enc in encodings.items():
            costs={mode:len(enc.encode(packed(p))) for mode,p in payloads.items()}
            overhead=len(enc.encode(packed(schemas)))+len(enc.encode(packed(follow)))
            results.append({'fixture':label,'profile':profile,'arguments':args,'same_evidence_and_provenance':True,'returned_count':len(hits),
                'compact_payload_tokens':costs['compact'],'ultra_payload_tokens':costs['ultra_compact'],
                'payload_reduction_pct':round(100*(1-costs['ultra_compact']/costs['compact']),2),
                'compact_bytes':len(packed(payloads['compact']).encode()),'ultra_bytes':len(packed(payloads['ultra_compact']).encode()),
                'schema_and_followup_tokens':overhead,'compact_workflow_tokens':costs['compact']+overhead,
                'ultra_workflow_tokens':costs['ultra_compact']+overhead,'metadata_hydration_calls':0})
    output={'tokenizer_library':'tiktoken','version':importlib.metadata.version('tiktoken'),'profiles':list(encodings),
      'scope':'Identical current-release evidence. tools/list includes the complete decoding legend; no extra contract/metadata hydration. One tool-discovery schema + one search + one bounded passage follow-up (context_chars=300); no metadata hydration needed. Excludes unavailable client/system wrapper and network serialization. Not a before/after retrieval-quality score.',
      'claude_usage':'Not measured; no Anthropic token-counting account supplied','results':results}
    path=ROOT/'verification'/SERVER_VERSION/'token_workflows.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(results,indent=2))
if __name__=='__main__':main()
