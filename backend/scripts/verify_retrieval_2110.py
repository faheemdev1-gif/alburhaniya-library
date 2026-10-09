#!/usr/bin/env python3
"""Replay disclosed development questions and independent wording probes.

Reference inclusion is a regression measure, not an answer-quality grade.
An externally owned, passage-graded set is needed to certify a 9/10 target.
"""
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.core import result_cache
from app.mcp_contract import SERVER_VERSION
from app.mcp_server import search_library


PARAPHRASES = [
    'كيف يتوب العبد من ذنوبه وهل يقبل الله توبته',
    'كيف يتوب الإنسان إذا أذنب وهل يغفر له',
    'ما الذي يجب على التائب فعله حتى تصح توبته',
    'كيف أرجع إلى الله بعد المعصية',
]


def run(query, **kwargs):
    result_cache.clear()
    start = time.perf_counter()
    response = search_library(query=query, limit=5, **kwargs)
    elapsed = round((time.perf_counter() - start) * 1000, 2)
    hits = response.get('results', [])
    return {'query': query, 'hits': [[h['book_id'], h['seq']] for h in hits],
            'elapsed_ms': elapsed, 'error': response.get('error'),
            'evidence_strength': response.get('evidence_strength'),
            'completion': response.get('completion')}


def main():
    fixture = json.loads((ROOT / 'tests/data/audit_270_regressions.json').read_text())['suite']
    previous = json.loads((ROOT / 'verification/2.10.10/replay.json').read_text())
    public = []
    for case in fixture:
        kwargs = {k: v for k, v in case['args'].items() if k not in ('query', 'limit')}
        row = run(case['query'], **kwargs)
        row['id'] = case['id']
        row['reference_in_top5'] = bool(
            {f'{book}:{seq}' for book, seq in row['hits']} & set(case['reference_pages'])
        )
        public.append(row)
    new_topics = [dict(id=case['id'], **run(case['query']))
                  for case in previous['new_topics']]
    paraphrases = []
    for query in PARAPHRASES:
        row = run(query)
        row['target_in_top5'] = ['b25', 137] in row['hits']
        paraphrases.append(row)
    # Save a reproducible disclosure, without labeling ungraded hits as answers.
    timings = sorted(row['elapsed_ms'] for row in public + new_topics + paraphrases)
    report = {'server_version': SERVER_VERSION,
              'scope': 'Local replay of disclosed development questions; reference inclusion only',
              'public': public, 'new_topics': new_topics, 'paraphrases': paraphrases,
              'summary': {'public_reference_top5': sum(r['reference_in_top5'] for r in public),
                          'public_total': len(public),
                          'new_topics_nonempty': sum(bool(r['hits']) for r in new_topics),
                          'new_topics_total': len(new_topics),
                          'paraphrases_target_top5': sum(r['target_in_top5'] for r in paraphrases),
                          'paraphrases_total': len(paraphrases),
                          'errors': sum(bool(r['error']) for r in public + new_topics + paraphrases),
                          'local_p95_ms': timings[math.ceil(.95 * len(timings)) - 1]}}
    output = ROOT / 'verification/2.10.10/final_replay.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
