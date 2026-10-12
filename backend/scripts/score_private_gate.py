#!/usr/bin/env python3
"""Score independently graded passage relevance without inventing labels.

Input is the JSON produced by evaluate_private_set.py after an independent
reviewer fills answerable, rank_grades, reviewer_id and review_status for each
query. Grades: 2 = directly answers the whole question; 1 = partial/topical;
0 = unrelated. A negative query should have answerable=false.
"""
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path


def score(source):
    if not source.get('owner'):
        raise ValueError('The private set needs an independent owner')
    questions=source.get('questions',[])
    by_intent=defaultdict(list)
    for q in questions:
        if not q.get('intent_id') or not q.get('query'):
            raise ValueError('Every query needs intent_id and query')
        by_intent[q['intent_id']].append(q)
        if q.get('review_status')!='graded' or not q.get('reviewer_id'):
            raise ValueError('Every response needs an independent passage review')
        if not isinstance(q.get('answerable'),bool):
            raise ValueError('Mark answerable explicitly, including negative controls')
        hits=q.get('response',{}).get('results',[])[:5]
        grades=q.get('rank_grades')
        if not isinstance(grades,list) or len(grades)!=len(hits) or any(type(g) is not int or g not in (0,1,2) for g in grades):
            raise ValueError('Give every returned top-five passage a 0/1/2 grade')
        for hit,grade in zip(hits,grades):
            if grade==2 and not all(key in hit for key in ('book_id','seq','match_id')):
                raise ValueError('Direct answers need an inspectable source locator')
    if len(by_intent)<100 or len(questions)<300:
        raise ValueError('The release standard requires at least 100 intents and three wordings each')
    if any(len({q['query'] for q in group})<3 for group in by_intent.values()):
        raise ValueError('Each intent needs three distinct Arabic wordings')
    if not {'definition','comparison','practice','colloquial','negation'} <= {q.get('form') for q in questions}:
        raise ValueError('Include all five required question forms')
    if not any(not q['answerable'] for q in questions):
        raise ValueError('Include source-gap or no-answer negative controls')
    if any(len({q['answerable'] for q in group})!=1 for group in by_intent.values()):
        raise ValueError('Wordings of one intent must share answerability')

    answerable=[q for q in questions if q['answerable']]
    negatives=[q for q in questions if not q['answerable']]
    if not answerable:raise ValueError('No answerable intents to score')
    direct=sum(2 in q['rank_grades'] for q in answerable)
    strict_intents=sum(all(2 in q['rank_grades'] for q in group)
                       for group in by_intent.values() if group[0]['answerable'])
    answerable_intents=sum(group[0]['answerable'] for group in by_intent.values())
    claims=[]
    for q in questions:
        for hit,grade in zip(q['response']['results'][:5],q['rank_grades']):
            if hit.get('question_relevance')=='relation_candidate':claims.append(grade==2)
    client=[float(q['client_ms']) for q in questions if isinstance(q.get('client_ms'),(int,float))]
    p95=sorted(client)[math.ceil(.95*len(client))-1] if len(client)==len(questions) else None
    return {
        'scope':'independently graded private set; passage-level directness',
        'intents':len(by_intent),'wordings':len(questions),'answerable_wordings':len(answerable),
        'negative_wordings':len(negatives),'direct_at5':round(direct/len(answerable),4),
        'all_three_direct_intent_rate':round(strict_intents/answerable_intents,4),
        'negative_weak_rate':round(sum(q['response'].get('evidence_strength')=='weak' for q in negatives)/len(negatives),4),
        'false_direct_claims_on_negatives':sum(any(hit.get('question_relevance')=='relation_candidate'
                                                 for hit in q['response']['results'][:5]) for q in negatives),
        'candidate_label_precision':round(sum(claims)/len(claims),4) if claims else None,
        'reviewed_candidate_labels':len(claims),
        'client_p95_ms':p95,
        'direct_at5_gate_75pct':'pass' if direct/len(answerable)>=.75 else 'fail',
        'label_gate_90pct':'pass' if len(claims)>=200 and sum(claims)/len(claims)>=.90 else 'unverified' if len(claims)<200 else 'fail',
        'overall_9plus':'unverified: other public, load, deployment and seven-day gates require separate evidence',
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('graded_json')
    parser.add_argument('output_json')
    args=parser.parse_args()
    report=score(json.loads(Path(args.graded_json).read_text()))
    Path(args.output_json).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
