#!/usr/bin/env python3
"""Run the complete regression suite and preserve failure evidence immediately."""
import importlib.metadata
import json
from pathlib import Path
import sys
import pytest
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.mcp_contract import SERVER_VERSION
OUT = ROOT / 'verification' / SERVER_VERSION
OUT.mkdir(parents=True, exist_ok=True)

class Evidence:
    def __init__(self):
        self.failures = []
        self.counts = {'passed': 0, 'failed': 0, 'skipped': 0}
        (OUT / 'test_failures.txt').write_text('')
        (OUT / 'failed_nodeids.json').write_text('[]\n')
    def pytest_runtest_logreport(self, report):
        if report.failed:
            self.failures.append(report.nodeid)
            with (OUT / 'test_failures.txt').open('a') as stream:
                stream.write(report.nodeid + '\n' + str(report.longrepr) + '\n\n')
            (OUT / 'failed_nodeids.json').write_text(json.dumps(self.failures, indent=2))
        if report.when == 'call' or (report.when == 'setup' and report.outcome != 'passed'):
            self.counts[report.outcome] = self.counts.get(report.outcome, 0) + 1
    def pytest_sessionfinish(self, session, exitstatus):
        versions = {name: importlib.metadata.version(name) for name in ('mcp','uvicorn','fastapi','pydantic','anyio','pytest')}
        (OUT / 'pytest_summary.json').write_text(json.dumps({'exit_code':int(exitstatus),
            'counts':self.counts, 'failed_nodeids':self.failures, 'runtime_versions':versions},indent=2)+'\n')

if __name__ == '__main__':
    raise SystemExit(pytest.main(['tests','-q','--disable-warnings','--durations=10', *sys.argv[1:]], plugins=[Evidence()]))
