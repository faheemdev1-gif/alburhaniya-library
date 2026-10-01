"""Full tool-boundary regression tests; no replacement of production settings."""
import unittest
from unittest.mock import patch
from app.services import library_db as db
from app.services.question_intent import content_terms, assess_window
from app.mcp_server import search_library, get_passage, get_page, get_book, list_books, mcp


class Release270Tests(unittest.TestCase):
    def test_function_words_do_not_count_as_question_intent(self):
        self.assertEqual(content_terms('كيف ينال من ضاقت عليه المعيشة سعة الرزق'),
                         ['ينال', 'ضاقت', 'المعيشة', 'سعة', 'الرزق'])
        result = assess_window('من ضاقت عليه المعيشة كيف ينال سعة الرزق',
            'كيف تظهر عليه سعة الرحمة', 15, 18, db._build_exact_variant_regex)
        self.assertIsNone(result)

    def test_livelihood_fixture_retains_relevant_sources_not_mercy_decoys(self):
        result = search_library(query='من ضاقت عليه المعيشة كيف ينال سعة الرزق', limit=5)
        ids = {(r['book_id'], r['seq']) for r in result['results']}
        self.assertTrue({('b41',130),('b41',131)} <= ids)
        self.assertFalse({('b40',51),('b39',324)} & ids)
        for hit in result['results']:
            row={**result.get('result_defaults',{}),**hit}
            self.assertFalse(row['answer_verified'])
            self.assertIn('reformulation_warning', row)
            page = db.get_page(row['book_id'],row['seq'])
            span = row['evidence_span']
            self.assertGreater(span['end'],span['start'])
            passage=get_passage(match_id=row['match_id'],context_chars=300)
            self.assertIn(page['text'][span['start']:min(span['end'],span['start']+50)],passage['passage'])

    def test_reformulation_pagination_is_stable(self):
        args = dict(query='من ضاقت عليه المعيشة كيف ينال سعة الرزق', ranking='relevance')
        whole = db.reformulated_search(**args, limit=6)
        parts = db.reformulated_search(**args,limit=3) + db.reformulated_search(**args,limit=3,offset=3)
        self.assertEqual([r['match_id'] for r in whole], [r['match_id'] for r in parts])

    def test_completeness_is_opt_in_without_counts(self):
        args = dict(query='طمأنينة',match_mode='lexeme',limit=2)
        self.assertEqual(search_library(**args)['retrieval_completeness']['status'],'not_checked')
        r = search_library(**args,check_completeness=True)
        self.assertEqual(r['retrieval_completeness']['method'],'actual_retrieved_candidates')
        self.assertEqual(r['retrieval_completeness']['status'],'ok')
        self.assertNotIn('literal_occurrences',r)

    def test_actual_search_omission_is_detected(self):
        literal = db._matching_page_ids(['طمأنينة'])
        book, seq = sorted(literal)[0]
        missing_text = db._indexable_text(db.get_page(book,seq)['text'])
        original = db._first_match
        def omit(text, pattern):
            return None if text == missing_text else original(text,pattern)
        with patch.object(db,'_first_match',side_effect=omit):
            r=search_library(query='طمأنينة',match_mode='lexeme',limit=20,check_completeness=True)
        self.assertTrue(r['results'])
        self.assertNotIn((book,seq),{(x['book_id'],x['seq']) for x in r['results']})
        self.assertEqual(r['retrieval_completeness']['status'],'warning')
        self.assertIn(f'{book}-p{seq}',r['retrieval_completeness']['missing_literal_page_sample'])
        self.assertTrue(r['diagnostics']['literal_inclusion_warning'])

    def test_equal_count_substitutions_are_detected_in_all_scopes(self):
        scopes = [dict(query='طمأنينة'),dict(queries=['إيمان','مسألة'],operator='OR'),
            dict(queries=['إيمان','مسألة'],operator='AND'),
            dict(query='طمأنينة',source_code='primary'),dict(query='الله',book_ids=['b38'])]
        original = db.record_candidates
        for args in scopes:
            with self.subTest(args=args):
                query = args.get('queries') or [args['query']]
                scope={k:v for k,v in args.items() if k in ('source_code','book_ids')}
                literals=db._matching_page_ids(query,operator=args.get('operator','OR'),**scope)
                self.assertTrue(literals)
                omitted=sorted(literals)[0]
                def substitute(ids,per_query=None):
                    ids=set(ids)
                    if omitted in ids:
                        ids.remove(omitted);ids.add(('b99',999))
                    changed={q:(set(v)-{omitted}) for q,v in (per_query or {}).items()}
                    original(ids,changed)
                with patch.object(db,'record_candidates',side_effect=substitute):
                    r=search_library(**args,match_mode='lexeme',limit=2,check_completeness=True)
                self.assertNotIn('error',r)
                self.assertEqual(r['retrieval_completeness']['status'],'warning')
                self.assertIn(f'{omitted[0]}-p{omitted[1]}',r['retrieval_completeness']['missing_literal_page_sample'])

    def test_score_filter_pagination_and_AND_are_not_omissions(self):
        for args in [dict(query='طمأنينة',min_score=1.0,offset=3),
                     dict(queries=['إيمان','مسألة'],operator='AND',offset=1)]:
            r=search_library(**args,match_mode='lexeme',limit=2,check_completeness=True)
            self.assertEqual(r['retrieval_completeness']['status'],'ok')
        self.assertEqual(search_library(query='طمأنينة',match_mode='lexeme',min_score=1.0,
                         check_completeness=True)['results'],[])

    def test_booleans_and_batch_provenance(self):
        self.assertIs(get_page('b38',1)['searchable_by_default'],False)
        self.assertIs(get_book('b38')['searchable_by_default'],False)
        self.assertIs(db.get_page('b14',246)['searchable_by_default'],True)
        full=list_books(projection='full',book_ids=['b38','b14'])
        self.assertEqual(full['total'],2)
        self.assertTrue(all(type(b['searchable_by_default']) is bool for b in full['books']))
        self.assertEqual(set(list_books(projection='ids',book_ids=['b38','b14'])['books']),{'b38','b14'})
        self.assertIn('error',list_books(book_ids=['b99']))

    def test_fresh_callable_schema_and_paragraph_selectors(self):
        schemas={t.name:t.parameters['properties'] for t in mcp._tool_manager.list_tools()}
        self.assertEqual(len(schemas),5)
        self.assertIn('check_completeness',schemas['search_library'])
        self.assertIn('projection',schemas['list_books'])
        single=get_passage(match_id='b11-p132-c304',context_mode='paragraph',max_chars=3000)
        batch=get_passage(match_ids=['b11-p132-c304'],context_mode='paragraph',max_chars=3000)['results'][0]
        self.assertEqual(single['passage'],batch['passage'])
        self.assertTrue(single['cross_page'])
        for result in (single,batch):
            for seg in result['context_segments']:
                source=db.get_page(seg['book_id'],seg['seq'])['text']
                self.assertEqual(result['passage'][seg['passage_start']:seg['passage_end']],
                                 source[seg['source_start']:seg['source_end']])
        stable=get_passage(stable_id='b14-q091-b010',context_mode='paragraph')
        self.assertNotIn('error',stable)
        self.assertEqual(get_passage(qasida_number=91)['returned_bayts'],22)
        self.assertIn('error',get_passage(match_id='b11-p132-c304',qasida_number=91))
        self.assertIn('error',get_passage(match_ids=['b11-p132-c304']*21))

    def test_text_cache_never_reuses_offsets_for_different_source(self):
        pattern=db._build_exact_variant_regex('طمأنينة')
        self.assertNotEqual(db._match_spans('طمأنينة',pattern), db._match_spans('نص طمأنينة',pattern))

    def test_http_health_and_all_five_tools(self):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as client:
            response=client.get('/health')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['server_version'],'2.10.5')
            self.assertEqual(response.json()['tool_count'],5)
            self.assertEqual(response.json()['corpus_contract']['status'],'ok')

    def test_unreviewed_questions_cannot_receive_a_score(self):
        from scripts.evaluate_questions import score_review
        with self.assertRaises(ValueError):
            score_review({'questions':[{'review_status':'pending','results':[]}]})

    def test_semantic_corpus_mismatch_is_not_activated(self):
        from app.services import semantic_search as semantic
        import numpy as np
        original=semantic._setting
        class Connection:
            def execute(self,*args):return self
            def fetchone(self):return (1,)
        with patch.object(semantic,'_setting',side_effect=lambda name,default:
                True if name=='enable_local_semantic_search' else original(name,default)), \
             patch.object(db,'_connection',return_value=Connection()), \
             patch.object(semantic,'_load_index',return_value=(np.zeros((2,3)),{'corpus_sha256':'old'})), \
             patch.object(semantic,'_semantic_corpus_identity',return_value=('new',2)):
            self.assertFalse(semantic.semantic_available())


if __name__=='__main__':
    unittest.main()
