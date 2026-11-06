"""Regression cases reproduced from the supplied 30 October run-2 report."""
import json
import re
import sqlite3
from time import perf_counter
from app.mcp_server import get_book, list_books, get_page, get_passage, search_library
from app.core import result_cache
from app.services import library_db as db


def test_metadata_defaults_are_small_and_diagnostics_are_opt_in():
    small = get_book('b14')
    full = get_book('b14', detail='full')
    assert 'connector_contract' not in small
    assert len(json.dumps(small, ensure_ascii=False)) < 1800
    assert 'connector_contract' in full
    batch = list_books(projection='full', book_ids=['b14', 'b38'])
    assert len(json.dumps(batch, ensure_ascii=False)) < 4000
    assert 'repeated_printed_labels' not in batch['corpus_contract']
    assert batch['corpus_contract']['books'] == 43
    assert 'repeated_printed_labels' in list_books(book_ids=['b14'], detail='full')['corpus_contract']


def test_passage_summary_keeps_offsets_without_duplicating_source_quote():
    small = get_passage(match_id='b39-p248-c1137')
    full = get_passage(match_id='b39-p248-c1137', detail='full')
    assert small['passage'] == full['passage']
    assert 'source_quote' not in small['source_span']
    assert 'source_quote' in full['source_span']
    assert small['source_span']['start'] == full['source_span']['start']
    assert 'phases_ms' not in small['timing']
    assert 'text_sha256' not in small['coordinate_contract']


def test_hamza_discovery_unions_both_spellings_but_preserves_literal_census():
    params = dict(limit=20, include_counts=True, diversify_books=False, detail='full')
    a = search_library(query='اسم الله الاعظم', **params)
    b = search_library(query='اسم الله الأعظم', **params)
    assert not a.get('error') and not b.get('error')
    assert a['effective_match_mode'] == b['effective_match_mode'] == 'spelling_discovery'
    assert {(h['book_id'], h['seq']) for h in a['results']} == {(h['book_id'], h['seq']) for h in b['results']}
    assert len(a['results']) >= 5
    assert a['literal_matching_pages'] != b['literal_matching_pages']
    from app.services.compact_response import decode_search_response
    assert all(h['answer_verified'] is False for h in decode_search_response(a)['results'])
    literal = search_library(query='اسم الله الاعظم', match_mode='exact', **params)
    assert literal['effective_match_mode'] == 'exact'
    assert literal['literal_matching_pages'] == a['literal_matching_pages']


def test_english_stopwords_and_context_are_bounded():
    result = search_library(query='what is dhikr', context_chars=40, detail='full')
    assert result['results']
    for hit in result['results']:
        marks = re.findall(r'<mark>(.*?)</mark>', hit['excerpt'])
        assert marks and all('dhikr' in term.lower() for term in marks)
        assert len(hit['excerpt']) < 300
    assert not db._build_highlight_regex('is').search('This wisdom exists')


def test_invalid_selectors_are_client_errors_with_useful_page_range(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services.traffic_metrics import traffic_summary
    monkeypatch.setattr(get_settings(), 'traffic_metrics_path', str(tmp_path / 'metrics.db'))
    unknown = get_book('b99')
    invalid = get_page('b14', 999)
    assert 'b14' in unknown['error']['message']
    assert '1–255' in invalid['error']['message']
    assert not {'retry', 'retry_scope', 'candidate_counts', 'stage'} & invalid.keys()
    summary = traffic_summary()
    assert summary['client_errors'] == 2 and summary['failed'] == 0


def test_lexeme_census_repeat_uses_result_cache():
    result_cache.clear()
    params = dict(query='ذكر', match_mode='lexeme', include_counts=True, limit=2, detail='full')
    first = search_library(**params)
    started = perf_counter()
    second = search_library(**params)
    elapsed = perf_counter() - started
    assert not first.get('error') and first['completion'] == 'full'
    assert second['cache']['status'] == 'hit'
    assert first['retrieval_hit_count'] == second['retrieval_hit_count']
    assert first['literal_occurrences'] == second['literal_occurrences']
    assert elapsed < 1


def test_parallel_analysis_does_not_read_conjunction_as_annihilation():
    from scripts.research_indexes import curated_analysis
    assert curated_analysis('فان')[1] != 'فني'
    assert curated_analysis('فناء')[1] == 'فني'


def test_footnote_blocks_agree_with_content_type():
    page = get_page('b14', 247)
    if 'footnote' in page['content_types']:
        assert any(block['type'] == 'footnote' for block in page['evidence_blocks'])


def test_utf8_ingestion_decodes_transport_entities(tmp_path):
    from scripts.book_parser import parse_utf8_pages
    source = tmp_path / 'book.json'
    source.write_text(json.dumps([{'paragraphs': ['It&#x27;s &quot;dhikr&quot;.']}]))
    assert parse_utf8_pages(str(source))[0]['paragraphs'] == ['It\'s "dhikr".']


def test_parallel_roots_have_source_witnesses_and_exclude_fain_false_positives():
    result = get_passage(stable_id='b14-q091-b002', include_parallels=True)
    assert not result.get('error')
    candidates = result['parallel_candidates']
    assert candidates
    assert not {'b14-q031-b018', 'b14-q056-b026'} & {item['candidate_stable_id'] for item in candidates}
    for item in candidates:
        for side in ('source', 'candidate'):
            assert all(item['root_evidence'][side][root] for root in json.loads(item['shared_roots']))
        assert item['citation_safe'] is False


def test_source_corruption_is_flagged_without_changing_the_quote():
    page = get_page('b39', 248)
    assert any(entry['status'] == 'original_scan_required' for entry in page['text_errata'])
    assert page['text'] == db.get_page('b39', 248)['text']
