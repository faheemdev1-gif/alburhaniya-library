"""Lossless evidence projection, cross-projection cache and build telemetry."""
import json
import sqlite3
import time
from copy import deepcopy
import pytest
from app.core import result_cache
from app.mcp_server import search_library
from app.services.compact_response import decode_search_response
from app.services import library_db as db

@pytest.mark.parametrize('args',[
 {'query':'الخلوة','match_mode':'exact','limit':6},
 {'queries':['الخلوة','المراقبة'],'match_mode':'terms','operator':'AND','limit':6},
 {'query':'ما العلامات التي تدل على صدق المريد في الطريق','limit':5},
 {'query':'الله','qasida_number':91,'match_mode':'exact','limit':5,'expand_top':2},
 {'query':'التوسل','book_ids':['b07'],'page_from':256,'page_to':256,'match_mode':'exact','limit':1},
 {'query':'الله','book_ids':['b01'],'page_from':153,'page_to':153,'match_mode':'exact','limit':2},
 {'query':'الخلوة','match_mode':'exact','offset':2,'limit':3},
])
def test_minimal_is_lossless_with_real_source_metadata(args):
 result_cache.clear()
 compact=search_library(**args)
 minimal=search_library(**args,mode='ultra_compact')
 assert not compact.get('error') and not minimal.get('error')
 assert minimal['encoding']=='lossless-15'
 assert decode_search_response(compact)==decode_search_response(minimal)
 for hit in decode_search_response(minimal)['results']:
  span=hit['evidence_span'];text=db.get_page(hit['book_id'],hit['seq'])['text']
  assert 0<=span['start']<span['end']<=len(text)
  assert hit['answer_verified'] is False


def test_canonical_cache_reuses_evidence_across_projection_detail_and_expansion(monkeypatch):
 result_cache.clear()
 a=search_library(query='الخلوة',match_mode='exact',limit=3)
 assert a['cache']['status']=='miss'
 def forbidden(*args,**kwargs):raise AssertionError('Retrieval repeated for a display change')
 monkeypatch.setattr(db,'search',forbidden)
 b=search_library(query='الخلوة',match_mode='exact',limit=3,mode='ultra_compact',detail='full',expand_top=1,expand_chars=250)
 assert not b.get('error') and b['cache']['status']=='hit'
 decoded=decode_search_response(b)
 assert decoded['results'][0]['expanded_passage']['passage']
 assert decoded['results'][0]['evidence_span']['source_quote']
 assert [(h['book_id'],h['seq']) for h in a['results']]==[(h['book_id'],h['seq']) for h in decoded['results']]
 b['results'].clear()
 c=search_library(query='الخلوة',match_mode='exact',limit=3)
 assert c['results'] and c['request_id']!=a['request_id']


def test_source_relation_route_preserves_reward_predicate():
 result_cache.clear()
 r=search_library(query='ماذا ينال من يحب سيدنا محمد',limit=5,detail='full')
 assert ('b01',62) in {(h['book_id'],h['seq']) for h in r['results']}
 assert any('predicate_surface' in f['routes'] for f in r['route_funnels'])


def test_indexed_features_have_canonical_local_offsets():
 for row in db._connection().execute('SELECT e.features,e.start_char,e.end_char,p.text FROM evidence_units e JOIN pages p ON p.id=e.page_id WHERE e.id%521=0'):
  features=json.loads(row['features']);text=row['text'][row['start_char']:row['end_char']]
  assert 'lexical_spans' in features and 'concept_spans' in features
  for surface,spans in features['lexical_spans'].items():
   for start,end in spans:assert text[start:end]==surface
  for spans in features['concept_spans'].values():
   for start,end,surface in spans:assert text[start:end]==surface


def test_traffic_window_does_not_mix_releases_or_idle_days(monkeypatch,tmp_path):
 from app.core.config import get_settings
 from app.mcp_contract import SERVER_VERSION
 from app.services.traffic_metrics import traffic_summary
 path=tmp_path/'attempts.sqlite3';monkeypatch.setattr(get_settings(),'traffic_metrics_path',str(path))
 now=time.time()
 with sqlite3.connect(path) as c:
  c.execute('CREATE TABLE attempts(request_id TEXT PRIMARY KEY,tool TEXT,build TEXT,execution TEXT,ms REAL,timestamp REAL)')
  c.executemany('INSERT INTO attempts VALUES(?,?,?,?,?,?)',[
   ('old','search_library','old-release','failed',99999,now-6*86400),
   ('new1','search_library',SERVER_VERSION,'full',10,now-3600),
   ('new2','search_library',SERVER_VERSION,'full',20,now-1800)])
 r=traffic_summary()
 assert r['build']==SERVER_VERSION and r['attempts_7d']==2 and r['failed']==0
 assert r['observed_days']<.03 and r['p95_ms']==20


def test_failed_index_rebuild_retains_the_previous_database(monkeypatch,tmp_path):
 from scripts import build_index
 target=tmp_path/'library.sqlite3'
 with sqlite3.connect(target) as c:c.execute('CREATE TABLE previous(value INTEGER)')
 before=target.read_bytes();monkeypatch.setattr(build_index,'DB_PATH',str(target))
 def fail():raise RuntimeError('injected ingestion failure')
 monkeypatch.setattr(build_index,'_build_database',fail)
 with pytest.raises(RuntimeError,match='injected'):build_index.build()
 assert target.read_bytes()==before


def test_index_publication_requires_integrity_and_no_foreign_journal(monkeypatch,tmp_path):
 from scripts import build_index
 target=tmp_path/'library.sqlite3';monkeypatch.setattr(build_index,'DB_PATH',str(target))
 def construct():
  with sqlite3.connect(build_index.DB_PATH) as c:c.execute('CREATE TABLE ready(value INTEGER)')
 monkeypatch.setattr(build_index,'_build_database',construct)
 build_index.build()
 with sqlite3.connect(target) as c:assert c.execute('PRAGMA quick_check').fetchone()[0]=='ok'
 prior=target.read_bytes();journal=tmp_path/'library.sqlite3-journal';journal.write_bytes(b'foreign transaction')
 with pytest.raises(RuntimeError,match='sidecars'):build_index.build()
 assert target.read_bytes()==prior


@pytest.mark.parametrize('query,match_mode',[
 ('الخلوة','exact'),('الخلوة المراقبة','terms'),('الأوراد','lexeme'),
 ('ماذا ينال من يحب سيدنا محمد','auto'),
])
def test_excerpt_contains_the_full_source_span_and_requested_context(query,match_mode):
 import html,re
 result_cache.clear()
 r=search_library(query=query,match_mode=match_mode,limit=5,context_chars=40,detail='full')
 assert not r.get('error') and r['results']
 for hit in r['results']:
  text=db.get_page(hit['book_id'],hit['seq'])['text'];span=hit['evidence_span']
  shown=html.unescape(re.sub(r'</?mark>','',hit['excerpt']))
  assert text[span['start']:span['end']] in shown
  assert len(shown)<=span['end']-span['start']+80+2
