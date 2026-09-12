"""Release gates from the two supplied September assessments."""
import itertools
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from app.services import library_db as db


class AssessmentFixTests(unittest.TestCase):
    def test_frozen_independent_literal_census_36_cases(self):
        fixture = json.loads((Path(__file__).parent/'data/assessment_literal_cases.json').read_text())
        for case in fixture['cases']:
            with self.subTest(query=case['query'], split=case['split']):
                scope = {'book_ids': case['book_ids']}
                expected = set(case['expected_literal_pages'])
                exact = {f'{b}-p{s}' for b,s in db._matching_page_ids([case['query']], **scope)}
                expanded = {f'{b}-p{s}' for b,s in db._matching_page_ids([case['query']], search_mode='lexeme', **scope)}
                self.assertEqual(exact, expected)
                self.assertTrue(expected <= expanded)
                self.assertEqual(db.search_stats([case['query']], **scope)['matching_occurrences'], case['expected_literal_occurrences'])

    def test_tumanina_literal_pages_are_all_retrieved(self):
        literal = db._matching_page_ids(['طمأنينة'])
        self.assertEqual(len(literal), 14)
        rows = db.search('طمأنينة', search_mode='lexeme', diversify_books=False, limit=10000)
        ids = {(x['book_id'], x['seq']) for x in rows}
        self.assertTrue(literal <= ids)
        self.assertEqual(db.search_stats(['طمأنينة'])['matching_occurrences'], 16)
        self.assertTrue({('b25', '32'), ('b11', '132'), ('b20', '246')} <=
                        {(r['book_id'], str(r['printed_page'])) for r in rows})

    def test_multi_query_maps_selected_span_all_orders_and_pages(self):
        for queries in (['أشرقت', 'فؤاد', 'ربك'], ['إيمان', 'مسألة']):
            reference = None
            scope = {'book_ids': ['b14']} if len(queries) == 3 else {}
            for ordering in itertools.permutations(queries):
                rows = db.search(queries=list(ordering), search_mode='lexeme',
                                 limit=6, diversify_books=False, **scope)
                found = {}
                for hit in rows:
                    span = hit['evidence_span']
                    text = db.get_page(hit['book_id'], hit['seq'])['text'][span['start']:span['end']]
                    self.assertTrue(hit['matched_terms'])
                    for query, term in hit['matched_terms'].items():
                        self.assertEqual(text, term['corpus_form'])
                        self.assertTrue(db._pattern_for_query(query, 'lexeme').fullmatch(text))
                    found[hit['match_id']] = hit['matched_terms']
                if reference is None:
                    reference = found
                self.assertEqual(reference, found)
                pages = []
                for offset in (0, 3):
                    pages += db.search(queries=list(ordering), search_mode='lexeme', limit=3,
                                       offset=offset, diversify_books=False, **scope)
                self.assertEqual([r['match_id'] for r in rows], [r['match_id'] for r in pages])
        q91 = db.search(queries=['أشرقت', 'فؤاد', 'ربك'], search_mode='lexeme',
                       book_ids=['b14'], qasida_number=91, limit=6)
        bayt = next(r for r in q91 if r.get('stable_id') == 'b14-q091-b010')
        self.assertEqual(list(bayt['matched_terms']), ['ربك'])

    def test_partial_omission_detected_even_with_equal_counts(self):
        literal = db._matching_page_ids(['طمأنينة'])
        omitted = sorted(literal)[0]
        seeded = literal - {omitted} | {('b99', 999)}
        report = db.literal_inclusion_report(['طمأنينة'], seeded)
        self.assertEqual(report['status'], 'warning')
        self.assertEqual(report['missing_literal_pages'], 1)
        self.assertIn(f'{omitted[0]}-p{omitted[1]}', report['missing_literal_page_sample'])

    def test_inclusion_per_query_and_pagination_independence(self):
        report = db.retrieval_completeness(['إيمان', 'مسألة'], 'lexeme')
        self.assertEqual(report['status'], 'ok')
        self.assertTrue(all(r['missing_literal_pages'] == 0 for r in report['per_query']))
        self.assertGreater(report['candidate_pages'], 3)
        self.assertEqual(len(db.search('طمأنينة', search_mode='lexeme', limit=3)), 3)

    def test_cross_page_paragraph_retains_original_locator_and_segments(self):
        pages = {
            1: {'book_id': 'b01', 'seq': 1, 'printed_page': '1', 'citation_label': 'p1',
                'text': 'first\n\nparagraph begins'},
            2: {'book_id': 'b01', 'seq': 2, 'printed_page': '2', 'citation_label': 'p2',
                'text': 'target continues'},
            3: {'book_id': 'b01', 'seq': 3, 'printed_page': '3', 'citation_label': 'p3',
                'text': 'paragraph ends\n\nnext'},
        }
        with patch.object(db, 'get_page', side_effect=lambda book, seq: pages.get(seq)):
            result = db._cross_page_paragraph(pages[2], 0, 6, 12000)
        self.assertTrue(result['complete_paragraph'])
        self.assertEqual(result['original_match']['seq'], 2)
        self.assertEqual(result['passage'], 'paragraph begins\ntarget continues\nparagraph ends')
        self.assertEqual([x['seq'] for x in result['context_segments']], [1, 2, 3])
        for segment in result['context_segments']:
            self.assertEqual(result['passage'][segment['passage_start']:segment['passage_end']],
                pages[segment['seq']]['text'][segment['source_start']:segment['source_end']])

    def test_cross_page_cap_does_not_claim_completion(self):
        page = {'book_id': 'b01', 'seq': 1, 'citation_label': 'p1', 'text': 'a' * 3000}
        with patch.object(db, 'get_page', return_value=None):
            result = db._cross_page_paragraph(page, 1500, 1501, 1000)
        self.assertFalse(result['complete_paragraph'])
        self.assertTrue(result['context_cap_applied'])
        self.assertLessEqual(len(result['passage']), 1000)
        self.assertGreaterEqual(result['passage_evidence_span']['start'], 0)

    def test_all_diwan_locators_preserve_page_boundaries(self):
        conn = db._connection()
        self.assertEqual(conn.execute('SELECT COUNT(DISTINCT qasida_number) FROM bayts').fetchone()[0], 95)
        rows = conn.execute('SELECT b.stable_id,b.start_char,b.end_char,b.bayt_number,p.text FROM bayts b JOIN pages p ON p.id=b.page_id')
        count = 0
        for row in rows:
            count += 1
            self.assertLess(row['start_char'], row['end_char'])
            self.assertLessEqual(row['end_char'], len(row['text']))
            self.assertTrue(row['text'][row['start_char']:row['end_char']].lstrip().startswith(str(row['bayt_number'])))
        self.assertEqual(count, 2682)
