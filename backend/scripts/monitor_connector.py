#!/usr/bin/env python3
"""Scheduled mixed HTTP samples. Exit nonzero above 1% failure."""
import argparse,asyncio,json,time,os
import fcntl
import tempfile
import math
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
CASES=[('list_books',{'projection':'ids'}),('get_book',{'book_id':'b07'}),('get_page',{'book_id':'b07','seq':166,'max_chars':200}),('get_passage',{'match_id':'b07-p166-c1180','context_chars':200})]+[('search_library',{'query':q,'limit':5,'include_counts':True}) for q in ['من ضاقت عليه المعيشة كيف ينال سعة الرزق','ماذا يفعل من ضاق رزقه واشتدت حاجته','كيف يتعامل المريد مع الحزن وضيق الصدر','ما النصيحة لمن يشعر بالهم والحزن','ما فضل الصلاة على النبي صلى الله عليه وسلم','ما هي الحقيقة المحمدية']]
async def run(url, count=20):
    if count < 1:
        raise ValueError("count must be positive")
    results = []
    session_error = None
    started = time.monotonic()
    key = os.environ.get("MCP_MONITOR_API_KEY")
    headers = {"Authorization": "Bearer " + key} if key else None

    def client_factory(**kwargs):
        return httpx.AsyncClient(**{**kwargs, "timeout": 25, "trust_env": False})

    try:
        async with streamablehttp_client(url, headers=headers, httpx_client_factory=client_factory) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for i in range(count):
                    name, args = CASES[i % len(CASES)]
                    start = time.monotonic()
                    data = {}
                    error = None
                    try:
                        reply = await session.call_tool(name, args)
                        data = reply.structuredContent
                        if not data and reply.content:
                            data = json.loads(reply.content[0].text)
                        data = data if isinstance(data, dict) else {}
                        if reply.isError or not data or data.get("error"):
                            error = data.get("error") or "invalid_tool_response"
                        elif name == "search_library" and data.get("completion") != "full":
                            error = "partial_completion"
                    except Exception as exc:
                        error = type(exc).__name__
                    results.append({"tool": name, "ok": error is None, "error": error,
                                    "request_id": data.get("request_id") if isinstance(data, dict) else None,
                                    "ms": round((time.monotonic()-start)*1000, 3)})
    except Exception as exc:
        session_error = type(exc).__name__

    def p95(rows):
        times = sorted(row["ms"] for row in rows)
        return times[math.ceil(len(times)*.95)-1] if times else None

    return {"timestamp": time.time(), "endpoint": url, "planned_calls": count,
            "calls": len(results), "unattempted": count-len(results),
            "successful": sum(row["ok"] for row in results), "session_error": session_error,
            "wall_ms": round((time.monotonic()-started)*1000, 3),
            "p95_ms": p95(results),
            "question_p95_ms": p95(r for r in results if r["tool"] == "search_library"),
            "results": results}

def append_history(path, report):
    """Retain complete observations across overlapping scheduled probes."""
    path = Path(path)
    with open(str(path) + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        history = json.loads(path.read_text()) if path.exists() else []
        if isinstance(history, dict):
            history = [history]
        cutoff = time.time() - 7 * 86400
        history = [sample for sample in history if sample["timestamp"] >= cutoff]
        history.append(report)
        with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as out:
            try:
                json.dump(history, out)
                out.flush()
                os.fsync(out.fileno())
                os.replace(out.name, path)
            finally:
                Path(out.name).unlink(missing_ok=True)

def main():
 p=argparse.ArgumentParser();p.add_argument('url');p.add_argument('--count',type=int,default=20);p.add_argument('--output',default='monitor-result.json');p.add_argument('--history');a=p.parse_args();report=asyncio.run(run(a.url,a.count));Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2))
 if a.history:
  append_history(a.history, report)
 print(json.dumps({k:v for k,v in report.items() if k!='results'}));return int(bool(report['session_error']) or report['unattempted'] > 0 or 1-report['successful']/report['planned_calls']>.01)
if __name__=='__main__':raise SystemExit(main())
