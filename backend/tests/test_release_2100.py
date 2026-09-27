"""Concrete 2.9 audit regressions; source-grounded, not a self-rated score."""
import json,time
from unittest.mock import patch
import pytest
from app.mcp_server import search_library,list_books,get_passage
from app.services import library_db as db
from app.core import result_cache
from app.core.budget import DEADLINE,BudgetExceeded

@pytest.fixture(autouse=True)
def clean_cache():result_cache.clear()

def test_detached_conjunction_symmetric_and_declared():
 a=search_library(query='الفناء والبقاء',match_mode='exact',limit=20,diversify_books=False)
 b=search_library(query='الفناء و البقاء',match_mode='exact',limit=20,diversify_books=False)
 assert {(h['book_id'],h['seq']) for h in a['results']}=={(h['book_id'],h['seq']) for h in b['results']}
 assert len(a['results'])==3
 assert any(e['relation']=='detached_conjunction' for h in a['results'] for e in h['matched_terms'].values())

def test_subject_outweighs_question_verb():
 r=search_library(query='ما فضل ليلة القدر وكيف نحييها',limit=5)
 assert (r['results'][0]['book_id'],r['results'][0]['seq'])==('b12',61)
 assert all('ليلة' in db.normalize_search_text(h['excerpt']) for h in r['results'][:3])

@pytest.mark.parametrize('query',['هل يكفي أن أقرأ الأوراد وأترك السعي للكسب','هل قراءة الأوراد تغني عن العمل لطلب الرزق','كيف نجمع بين الأوراد والسعي لكسب العيش'])
def test_answer_above_grouped_biography(query):
 r=search_library(query=query,limit=5)
 assert (r['results'][0]['book_id'],r['results'][0]['seq'])==('b41',131)
 biographies=[h for h in r['results'] if (h['book_id'],h['seq']) in {('b42',4),('b39',5)}]
 assert len(biographies)<=1
 if biographies:assert biographies[0]['also_in'] and biographies[0]['question_relevance']=='topic_only'

def test_weak_coverage_no_root_filler():
 r=search_library(query='إزاي أربي ولادي تربية صالحة',limit=5)
 assert r['evidence_strength']=='weak'
 assert {(h['book_id'],h['seq']) for h in r['results']}=={('b44',29),('b44',35)}

def test_quoted_opponent_warning_survives_compaction():
 for mode in ['compact','ultra_compact']:
  r=search_library(query='ما حكم زيارة قبور الأولياء والتوسل بهم',limit=5,mode=mode)
  h=next(h for h in r['results'] if (h.get('book_id',h.get('b')),h.get('seq',h.get('s')))==('b07',256))
  assert h['reported_view'] and h['attribution_warning']

def test_metadata_explicit_per_hit_and_hadith_not_quran():
 r=search_library(query='كيف يبر الإنسان والديه بعد موتهما',limit=5)
 h=r['results'][0];assert h['question_relevance']=='relation_candidate'
 for text in ['وقال ﷺ: ﴿ مَنْ لَزِمَ الِاسْتِغْفَارَ جَعَلَ اللهُ لَهُ فَرَجًا ﴾','قال النبي: ﴿ حديث طويل للاختبار هنا ﴾']:
  start=text.index('﴿')+2;assert db.evidence_type(text,start,start+1)=='hadith'
 assert db.evidence_type('قال تعالى: ﴿ إن مع العسر يسرا ﴾',15,16)=='quran'
 assert db.evidence_type('في الخطبة أجاب الرجل ثم تلا كلاما مفيدا',25,26)=='body'

def test_partial_evidence_survives_later_deadline():
 query='ما فضل الصلاة على النبي صلى الله عليه وسلم'
 def timeout(*a,**kw):
  DEADLINE.set(time.monotonic()-1);raise BudgetExceeded()
 with patch('app.services.question_search.passage_candidates',side_effect=timeout):r=search_library(query=query,limit=5)
 assert not r.get('error') and r['results'] and r['completion']=='partial'
 assert r['stages_skipped'] and r['candidate_counts']['phrase_candidates']>0

def test_error_timing_and_retry_are_present():
 r=search_library(query='طمأنينة',match_mode='lexeme',min_tier=9)
 assert r['error'] and r['timing'] and r['stage'] and 'candidate_counts' in r
 assert r['retry']['match_mode']=='exact'

def test_census_literal_subset():
 r=search_library(query='طمأنينة',match_mode='lexeme',include_counts=True,limit=5)
 assert r['literal_matching_pages']==db.search_stats(['طمأنينة'])['surface_matching_pages'] and r['retrieval_hit_count']==20
 assert r['retrieval_completeness']['missing_literal_pages']==0

def test_cache_isolated_and_controls_bound():
 a=search_library(query='ليلة القدر',limit=2);a['results'].clear()
 b=search_library(query='ليلة القدر',limit=2)
 assert b['results'] and b['cache']['status']=='hit' and b['request_id']!=a['request_id']
 assert search_library(query='ليلة القدر',limit=3)['cache']['status']=='miss'
 assert search_library(query='ليلة القدر',limit=2,check_completeness=True).get('cache',{}).get('status')!='hit'

def test_ids_payload_budget():
 r=list_books(projection='ids',book_ids=['b14','b41'])
 assert r['books']==['b14','b41'] and len(json.dumps(r,ensure_ascii=False).encode())<1024
 assert 'corpus_contract' not in r

def test_qasida_91_preserved():
 r=get_passage(qasida_number=91)
 assert 'error' not in r
