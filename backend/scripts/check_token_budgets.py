#!/usr/bin/env python3
"""CI gate for equivalent-evidence response size; no retrieval quality grading."""
import argparse,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from app.mcp_contract import SERVER_VERSION

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,default=ROOT/'verification'/SERVER_VERSION/'token_workflows.json')
 parser.add_argument('--baseline',type=Path,default=ROOT/'tests/data/token_budgets_2116.json');args=parser.parse_args()
 current=json.loads(args.report.read_text());baseline=json.loads(args.baseline.read_text())
 limits={(r['fixture'],r['profile']):r for r in baseline['controls']};seen=set();failures=[]
 for r in current['results']:
  key=(r['fixture'],r['profile'])
  if key in seen:failures.append(f'Duplicated control {key}')
  seen.add(key)
  if key not in limits:failures.append(f'Unknown control {key}');continue
  old=limits[key]
  if not r['same_evidence_and_provenance']:failures.append(f'Evidence changed: {key}')
  if r['returned_count']!=old['returned_count']:failures.append(f'Returned count changed: {key}')
  for metric in ('compact_payload_tokens','ultra_payload_tokens'):
   cap=math.ceil(old[metric]*(1+baseline['maximum_growth_pct']/100))
   if r[metric]>cap:failures.append(f'{key} {metric}: {r[metric]} exceeds {cap}; an explained baseline revision is required')
  if r['fixture']=='six_hit_lexical' and (r['returned_count']!=6 or r['payload_reduction_pct']<25):failures.append(f'Six-hit 25% target missed: {key}')
  if r['fixture']=='one_hit_question' and r['ultra_bytes']>1500:failures.append(f'One-hit 1500-byte target missed: {key}')
 if seen!=set(limits):failures.append('Missing or duplicated/unknown benchmark controls')
 print(json.dumps({'status':'fail' if failures else 'pass','controls':len(seen),'failures':failures},indent=2))
 if failures:raise SystemExit(1)
if __name__=='__main__':main()
