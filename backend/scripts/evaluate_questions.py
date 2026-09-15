#!/usr/bin/env python3
"""Export blinded-review candidates, then score only externally reviewed labels."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


def score_review(review):
    items=review['questions']
    if not items or any(q.get('review_status')!='reviewed' or not q.get('reviewer') for q in items):
        raise ValueError('Independent reviewer identity and reviewed status are required for every question')
    values=[]
    for question in items:
        hits=question['results']
        if any(type(r.get('relevance_grade')) is not int or r['relevance_grade'] not in (0,1,2)
               or not r.get('review_note') for r in hits):
            raise ValueError('Every result needs grade 0/1/2 and an evidence-based review_note')
        values.append(sum(r['relevance_grade']==2 for r in hits[:5])/5)
    return {'questions':len(values),'mean_precision_at_5':sum(values)/len(values),
            'definition':'Grade 2 directly addresses the question; grade 1 is only a topic match; grade 0 is irrelevant. Missing hits count as not relevant. Not the external weighted connector score.'}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--split',choices=['development','held_out'],default='development')
    p.add_argument('--output',default='verification/question_review.json')
    p.add_argument('--score-review')
    args=p.parse_args()
    if args.score_review:
        print(json.dumps(score_review(json.loads(Path(args.score_review).read_text())),indent=2))
    else:
        from app.mcp_server import search_library, get_passage
        questions=json.loads((ROOT/'data/research_questions.json').read_text())['questions']
        out=[]
        for q in questions:
            if q['split']!=args.split:continue
            result=search_library(query=q['query'],limit=5)
            if result.get('error'):raise RuntimeError(result['error'])
            row=dict(q,reviewer=None,results=[])
            for hit in result['results']:
                row['results'].append({'book_id':hit['book_id'],'seq':hit['seq'],
                    'match_id':hit['match_id'],'citation_label':hit.get('citation_label'),
                    'passage':get_passage(match_id=hit['match_id'],context_mode='paragraph',max_chars=3000),
                    'relevance_grade':None,'review_note':None})
            out.append(row)
        Path(args.output).parent.mkdir(parents=True,exist_ok=True)
        Path(args.output).write_text(json.dumps({'split':args.split,'questions':out},ensure_ascii=False,indent=2)+'\n')
        print(f'Exported {len(out)} questions for independent review. No relevance score assigned.')
