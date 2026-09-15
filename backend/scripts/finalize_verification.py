#!/usr/bin/env python3
"""Run final checks, preserve exact outputs, and fail on any check failure."""
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
ROOT=Path(__file__).resolve().parent.parent
os.chdir(ROOT)
out=ROOT/'verification';out.mkdir(exist_ok=True)
commands=[('pytest',[sys.executable,'-m','pytest','-q']),
          ('classified_suite',[sys.executable,'scripts/run_regression_suite.py']),
          ('corpus_audit',[sys.executable,'scripts/independent_corpus_audit.py','library.db']),
          ('negative_control',[sys.executable,'scripts/prove_audit_failure.py']),
          ('assessment_release',[sys.executable,'scripts/verify_assessment_release.py','--runs','7','--output','verification/assessment_release.json'])]
records=[]
for name,command in commands:
    result=subprocess.run(command,capture_output=True,text=True)
    (out/f'{name}.log').write_text(result.stdout+'\n'+result.stderr)
    records.append({'check':name,'command':command,'exit_code':result.returncode})
    print(f'{name}: '+('PASS' if result.returncode==0 else 'FAIL'),flush=True)
    if result.returncode:
        print(result.stdout[-4000:]+result.stderr[-4000:],flush=True)
        break
freeze=subprocess.run([sys.executable,'-m','pip','freeze'],capture_output=True,text=True)
(out/'tested_environment.txt').write_text(freeze.stdout)
result={'python':platform.python_version(),'platform':platform.platform(),
        'check_results':records,'passed':len(records)==len(commands) and all(r['exit_code']==0 for r in records),
        'production_deployed':False,'docker_engine_tested':False}
(out/'final_checks.json').write_text(json.dumps(result,indent=2)+'\n')
sys.exit(0 if result['passed'] else 1)
