#!/usr/bin/env python3
"""External-owner runner. Private questions stay on the reviewer's machine."""
import argparse,asyncio,json,os
from pathlib import Path
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
async def run(endpoint,source):
 if not source.get('independent_owner'):raise ValueError('An independent owner must identify the private set')
 questions=source['questions'];groups={}
 if len(questions)<40:raise ValueError('Require at least 40 independently owned questions')
 required={'definition','comparison','practice','colloquial','negation'}
 if not required<={q.get('form') for q in questions}:raise ValueError('Include definition, comparison, practice, colloquial and negation forms')
 out=[]
 headers={'Authorization':'Bearer '+os.environ['MCP_MONITOR_API_KEY']} if os.environ.get('MCP_MONITOR_API_KEY') else None
 async with streamablehttp_client(endpoint,headers=headers) as (read,write,_):
  async with ClientSession(read,write) as session:
   await session.initialize()
   for q in questions:
    r=await session.call_tool('search_library',{'query':q['query'],'limit':5,'detail':'full'});payload=r.structuredContent or json.loads(r.content[0].text);out.append({**q,'response':payload,'review_status':'pending','rank_grades':None})
 return {'scope':'private externally owned set; requires evidence-based grading','owner':source['independent_owner'],'questions':out}
def main():
 p=argparse.ArgumentParser();p.add_argument('endpoint');p.add_argument('input');p.add_argument('output');a=p.parse_args();Path(a.output).write_text(json.dumps(asyncio.run(run(a.endpoint,json.loads(Path(a.input).read_text()))),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
