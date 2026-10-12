#!/usr/bin/env python3
"""Strict, independently reviewed retrieval gate; never manufactures relevance.

Run evaluate_private_set.py first. The owner grades each top-five hit 0/1/2,
marks wrong_sense_ranks, coverage_registered and records the public-suite gate.
The homograph cases may be a subset of answerable intents. A previous passing
report is required to establish two consecutive releases.
"""
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path


def _rate(n, d):
    return round(n / d, 4) if d else None


def score(source, previous=None):
    if not source.get('owner') or not source.get('release'):
        raise ValueError('An independent owner and release are required')
    groups = defaultdict(list)
    negatives = []
    weak = []
    homographs = []
    for q in source.get('questions', []):
        if not q.get('intent_id') or not q.get('query') or q.get('review_status') != 'graded' or not q.get('reviewer_id'):
            raise ValueError('Every query needs an intent, wording and independent review')
        kind = q.get('set_kind', 'answerable')
        if kind not in ('answerable', 'negative', 'weak'):
            raise ValueError('set_kind must be answerable, negative or weak')
        hits = q.get('response', {}).get('results', [])[:5]
        grades = q.get('rank_grades')
        if not isinstance(grades, list) or len(grades) != len(hits) or any(type(g) is not int or g not in (0, 1, 2) for g in grades):
            raise ValueError('Grade every returned top-five hit 0, 1 or 2')
        wrong = q.get('wrong_sense_ranks', [])
        if not isinstance(wrong, list) or any(type(r) is not int or r < 1 or r > len(hits) for r in wrong):
            raise ValueError('wrong_sense_ranks must identify returned top-five ranks')
        if any(grades[r - 1] != 0 for r in wrong):
            raise ValueError('Wrong-sense passages must have relevance grade 0')
        if any(g == 2 and not all(k in hit for k in ('book_id', 'seq', 'match_id')) for hit, g in zip(hits, grades)):
            raise ValueError('Direct answers require inspectable source locators')
        if kind == 'answerable':
            groups[q['intent_id']].append(q)
        elif kind == 'negative':
            negatives.append(q)
        else:
            weak.append(q)
        if q.get('homograph_case'):
            homographs.append(q)
    if len(groups) < 300 or any(len(group) != 3 or len({q['query'] for q in group}) != 3 for group in groups.values()):
        raise ValueError('At least 300 answerable intents, exactly three distinct wordings each, are required')
    if len({q['intent_id'] for q in negatives}) < 50 or len({q['intent_id'] for q in weak}) < 50:
        raise ValueError('At least 50 independent negative and 50 weak-coverage intents are required')
    if len(homographs) < 100 or any('wrong_sense_ranks' not in q for q in homographs):
        raise ValueError('At least 100 explicitly reviewed homograph cases are required')
    if any(q.get('coverage_registered') is not True for q in weak):
        raise ValueError('Every weak-coverage intent needs a reviewed coverage-register entry')
    answerable = [q for group in groups.values() for q in group]
    if not {'meaning', 'difference', 'virtue', 'stance', 'remedy', 'signs', 'when_how', 'biography'} <= {q.get('answer_type') for q in answerable}:
        raise ValueError('All eight answer types must occur in the private set')
    direct1 = _rate(sum(q['rank_grades'][:1] == [2] for q in answerable), len(answerable))
    direct5 = _rate(sum(2 in q['rank_grades'] for q in answerable), len(answerable))
    stable = _rate(sum(all(2 in q['rank_grades'] for q in group) for group in groups.values()), len(groups))
    def ndcg(q):
        grades = q['rank_grades']
        ideal = q.get('ideal_top5_grades')
        if not isinstance(ideal, list) or len(ideal) != 5 or any(type(g) is not int or g not in (0, 1, 2) for g in ideal):
            raise ValueError('Independent ideal_top5_grades (five 0/1/2 grades) required for nDCG')
        if ideal != sorted(ideal, reverse=True):
            raise ValueError('ideal_top5_grades must be sorted descending')
        dcg = lambda values: sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(values))
        if dcg(grades) > dcg(ideal) + 1e-9:
            raise ValueError('Observed DCG exceeds the reviewed ideal; fix the judgments')
        return dcg(grades) / dcg(ideal) if dcg(ideal) else 0
    ndcg5 = round(sum(ndcg(q) for q in answerable) / len(answerable), 4)
    # Precision counts returned passages, not padded empty slots.
    hits = [g for q in answerable for g in q['rank_grades']]
    precision = _rate(sum(g > 0 for g in hits), len(hits))
    controls = negatives + weak
    negative_rate = _rate(sum(not q['response'].get('results') or q['response'].get('evidence_strength') == 'weak' for q in negatives), len(negatives))
    weak_rate = _rate(sum(q['response'].get('evidence_strength') == 'weak' for q in weak), len(weak))
    homograph_rate = _rate(sum(bool(q['wrong_sense_ranks']) for q in homographs), len(homographs))
    claims = [(g == 2) for q in answerable + controls for hit, g in zip(q['response']['results'][:5], q['rank_grades']) if hit.get('question_relevance') == 'relation_candidate']
    label_precision = _rate(sum(claims), len(claims))
    external = source.get('external_gates', {})
    gates = {
        'direct_at5': direct5 >= .95, 'direct_at1': direct1 >= .75,
        'wording_stability': stable >= .90, 'ndcg_at5': ndcg5 >= .88,
        'precision_at5': precision is not None and precision >= .90,
        'negative_controls': negative_rate == 1, 'homograph_errors': homograph_rate <= .02,
        'weak_coverage': weak_rate == 1,
        'public_suite': external.get('public_suite_pass') is True,
        'familiar_suite': external.get('familiar_suite_pass') is True,
        'zero_regressions': external.get('zero_regressions') is True,
    }
    current_pass = all(gates.values())
    previous_pass = bool(previous and previous.get('single_release_gate') is True and previous.get('release') != source['release'])
    return {'release': source['release'], 'owner': source['owner'], 'answerable_intents': len(groups),
            'answerable_wordings': len(answerable), 'negative_intents': len({q['intent_id'] for q in negatives}),
            'weak_intents': len({q['intent_id'] for q in weak}), 'homograph_cases': len(homographs),
            'direct_at1': direct1, 'direct_at5': direct5, 'wording_stability': stable,
            'ndcg_at5': ndcg5, 'precision_at5': precision, 'negative_pass_rate': negative_rate,
            'weak_coverage_rate': weak_rate, 'homograph_error_rate': homograph_rate,
            'candidate_label_precision': label_precision, 'reviewed_candidate_labels': len(claims),
            'gates': gates, 'single_release_gate': current_pass,
            'two_consecutive_release_gate': current_pass and previous_pass}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('graded_json')
    parser.add_argument('output_json')
    parser.add_argument('--previous', help='Previous independently scored release report')
    args = parser.parse_args()
    data = json.loads(Path(args.graded_json).read_text())
    previous = json.loads(Path(args.previous).read_text()) if args.previous else None
    report = score(data, previous)
    Path(args.output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
