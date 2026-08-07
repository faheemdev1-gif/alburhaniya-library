import os
import sys
import types
import unittest
import json

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND_DIR)

# Keep these database-level tests independent of the web-server dependencies.
config_stub = types.ModuleType("app.core.config")
config_stub.get_settings = lambda: types.SimpleNamespace(
    library_db_path=os.path.join(BACKEND_DIR, "library.db")
)
sys.modules["app.core.config"] = config_stub

from app.services import library_db as db
from app.services.compact_response import compact_search_response


class CompactRetrievalTests(unittest.TestCase):
    def test_search_returns_snippets_not_full_pages(self):
        results = db.search("الله", limit=3)
        self.assertTrue(results)
        for result in results:
            self.assertIn("snippet", result)
            self.assertNotIn("text", result)
            self.assertNotIn("highlight", result)
            self.assertLessEqual(len(result["snippet"]), 400)

    def test_book_and_source_filters(self):
        results = db.search("الله", book_ids=["b14"], source_code="primary", limit=5)
        self.assertTrue(results)
        self.assertTrue(all(item["book_id"] == "b14" for item in results))
        self.assertTrue(all(item["source_code"] == "primary" for item in results))

    def test_legacy_full_text_is_opt_in(self):
        result = db.search("الله", limit=1, include_full_text=True)[0]
        self.assertIn("text", result)
        self.assertIn("highlight", result)

    def test_page_range_filter(self):
        results = db.search("الله", page_from=1, page_to=10, limit=20)
        self.assertTrue(all(1 <= item["seq"] <= 10 for item in results))

    def test_offset_paginates_without_overlap(self):
        first = db.search("الله", limit=2, offset=0)
        second = db.search("الله", limit=2, offset=2)
        first_keys = {(x["book_id"], x["seq"]) for x in first}
        second_keys = {(x["book_id"], x["seq"]) for x in second}
        self.assertFalse(first_keys & second_keys)

    def test_v2_compact_shape_deduplicates_book_metadata(self):
        rows = db.search("الله", limit=8, context_chars=120)
        payload = compact_search_response(rows, limit=8, offset=0, has_more=False)
        self.assertTrue(payload["results"])
        self.assertTrue(payload["books"])
        for hit in payload["results"]:
            self.assertNotIn("book_title", hit)
            self.assertNotIn("source_code", hit)
            self.assertNotIn("page_number", hit)
            self.assertNotIn("page_label", hit)
            self.assertIn(hit["book_id"], payload["books"])

    def test_v2_payload_is_smaller_than_standard_rows(self):
        rows = db.search("الله", limit=8, context_chars=120)
        compact = json.dumps(
            compact_search_response(rows, limit=8, offset=0, has_more=False),
            ensure_ascii=False,
        )
        standard = json.dumps({"results": rows}, ensure_ascii=False)
        self.assertLess(len(compact), len(standard) * 0.9)

    def test_total_hits_is_true_count(self):
        total = db.count_search(["المريد"])
        rows = db.search("المريد", limit=3)
        self.assertGreaterEqual(total, len(rows))

    def test_diversifies_across_books(self):
        rows = db.search("المريد", limit=6, diversify_books=True, max_per_book=2)
        counts = {}
        for row in rows:
            counts[row["book_id"]] = counts.get(row["book_id"], 0) + 1
        self.assertTrue(all(n <= 2 for n in counts.values()))

    def test_multiple_query_or_search(self):
        rows = db.search(queries=["مدد", "إمداد"], operator="OR", limit=5)
        self.assertTrue(rows)

    def test_vowelled_query_centres_excerpt(self):
        rows = db.search("اللّٰه", limit=1, context_chars=80)
        self.assertTrue(rows)
        self.assertIn("<mark>", rows[0]["snippet"])

    def test_get_passage_is_bounded(self):
        hit = db.search("المريد", limit=1)[0]
        passage = db.get_passage_by_match_id(hit["match_id"], 300)
        self.assertIsNotNone(passage)
        self.assertLessEqual(len(passage["passage"]), 750)
        self.assertEqual(passage["match_id"], hit["match_id"])

    def test_every_search_hit_has_stable_match_id_and_score(self):
        first = db.search("المريد", limit=3)
        second = db.search("المريد", limit=3)
        self.assertEqual([x["match_id"] for x in first], [x["match_id"] for x in second])
        self.assertTrue(all("score" in x for x in first))

    def test_title_scope_resolves_series_without_catalogue(self):
        self.assertEqual(db.resolve_book_scope("شرح شراب الوصل"), [
            "b20", "b21", "b22", "b23", "b24", "b25"
        ])
        self.assertEqual(db.resolve_book_scope("تبرئة الذمة"), ["b10", "b11", "b12", "b13"])

    def test_hybrid_recovers_separated_terms(self):
        exact = db.search("الصلاة في وقتها", search_mode="exact_phrase", limit=5)
        hybrid = db.hybrid_search(queries=["الصلاة في وقتها"], limit=5)
        self.assertFalse(exact)
        self.assertTrue(hybrid)

    def test_compact_response_omits_counts_by_default(self):
        rows = db.search("الله", limit=2)
        payload = compact_search_response(rows, limit=2, offset=0, has_more=True)
        self.assertNotIn("total_hits", payload)
        self.assertNotIn("total_occurrences", payload)
        self.assertIn("next_offset", payload)

    def test_single_book_search_is_not_diversified(self):
        total = db.count_search(["الله"], book_ids=["b14"])
        self.assertGreaterEqual(total, 8)
        rows = db.search("الله", book_ids=["b14"], limit=8, diversify_books=True, max_per_book=2)
        self.assertEqual(len(rows), 8)
        self.assertTrue(all(row["book_id"] == "b14" for row in rows))

    def test_search_modes(self):
        phrase = db.search("صلى الله", search_mode="exact_phrase", limit=3)
        all_words = db.search("الله المريد", search_mode="all_words", limit=3)
        any_word = db.search("لفظغيرموجود الله", search_mode="any_word", limit=3)
        self.assertTrue(phrase)
        self.assertTrue(all_words)
        self.assertTrue(any_word)

    def test_lexeme_mode_recovers_affixed_hima_forms(self):
        exact = db.search_stats(["حمى"], book_ids=["b14"])
        enumerated = db.search_stats(
            ["حمى", "الحمى", "حماك", "حماه", "حماية", "حمانا"],
            operator="OR", book_ids=["b14"],
        )
        lexeme = db.search_stats(["حمى"], book_ids=["b14"], search_mode="lexeme")
        self.assertEqual(exact["matching_pages"], 7)
        self.assertEqual(enumerated["matching_pages"], 16)
        self.assertGreaterEqual(lexeme["matching_pages"], enumerated["matching_pages"])

    def test_search_stats_distinguish_pages_occurrences_and_terms(self):
        stats = db.search_stats(["حمى", "الحمى"], operator="OR", book_ids=["b14"])
        self.assertEqual(stats["matching_pages"], 14)
        self.assertGreater(stats["matching_occurrences"], stats["matching_pages"])
        self.assertEqual([x["query"] for x in stats["per_query"]], ["حمى", "الحمى"])
        self.assertTrue(all("matching_pages" in x and "occurrences" in x for x in stats["per_query"]))

    def test_khitabat_have_citation_labels(self):
        self.assertTrue(db.get_page("b44", 1)["citation_label"])
        self.assertTrue(db.get_page("b45", 1)["citation_label"])

    def test_numeric_tiers_preserve_internal_primary_order(self):
        self.assertEqual(db.get_book("b26")["source_tier"], 2)
        self.assertEqual(db.get_book("b42")["source_tier"], 3)
        self.assertEqual(db.get_book("b44")["source_tier"], 3)
        self.assertLess(db.get_book("b26")["source_tier"], db.get_book("b42")["source_tier"])
        self.assertEqual(set(db.get_tiers()), {"1", "2", "3", "4", "5"})

    def test_ultra_compact_shape(self):
        rows = db.search("الله", limit=4)
        payload = compact_search_response(rows, limit=4, offset=0, has_more=False, ultra=True)
        self.assertIn("n", payload)
        self.assertIn("books", payload)
        self.assertIn("b", payload["results"][0])
        self.assertIn("x", payload["results"][0])

    def test_persian_character_normalization(self):
        from app.core.arabic_utils import normalize_arabic
        self.assertEqual(normalize_arabic("ک ی ے"), "ك ي ي")


if __name__ == "__main__":
    unittest.main()
