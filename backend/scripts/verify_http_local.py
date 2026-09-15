#!/usr/bin/env python3
"""Run the existing production checks against an isolated local HTTP server."""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import httpx
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT));os.chdir(ROOT)
from scripts.production_mcp_regression import run


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    (ROOT/'verification').mkdir(exist_ok=True)
    with (ROOT/'verification/local_http_server.log').open('w') as log:
        server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app',
            '--host','127.0.0.1','--port',str(port),'--log-level','error'],stdout=log,stderr=log)
        try:
            with httpx.Client(trust_env=False) as client:
                for _ in range(100):
                    if server.poll() is not None:raise RuntimeError('Local server stopped before readiness')
                    try:
                        if client.get(f'http://127.0.0.1:{port}/health',timeout=1).status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.1)
                else:raise RuntimeError('Local server readiness timeout')
            report=asyncio.run(run(f'http://127.0.0.1:{port}/mcp/',False))
            report['deployment_scope']='local isolated HTTP server, not the live deployment'
            (ROOT/'verification/local_http.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps(report,ensure_ascii=False,indent=2))
        finally:
            server.terminate()
            try:server.wait(timeout=10)
            except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=='__main__':main()
