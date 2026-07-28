import os
import sys
import types
import unittest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND_DIR)

# Keep these database-level tests independent of the web-server dependencies.
config_stub = types.ModuleType("app.core.config")
config_stub.get_settings = lambda: types.SimpleNamespace(
    library_db_path=os.path.join(BACKEND_DIR, "library.db")
)
sys.modules["app.core.config"] = config_stub

from app.services import library_db as db


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


if __name__ == "__main__":
    unittest.main()
