import json
import os
import sqlite3
import unittest

from app.services.corpus_contract import corpus_contract_snapshot


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(ROOT, "library.db")


class ResearchIndexHardGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = sqlite3.connect(DB_PATH)
        cls.conn.row_factory = sqlite3.Row

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_hard_live_corpus_contract_is_computed_from_database(self):
        snapshot = corpus_contract_snapshot(DB_PATH)
        self.assertEqual(snapshot["status"], "ok")
        self.assertEqual(snapshot["books"], 43)
        self.assertEqual(snapshot["edition_deduplication"]["status"], "ok")
        self.assertEqual(snapshot["edition_deduplication"]["default_search_books"], 42)
        self.assertEqual(snapshot["edition_deduplication"]["default_search_pages"], 6885)
        self.assertEqual(snapshot["edition_deduplication"]["canonical_aliases"], {"b38": "b37"})
        self.assertEqual(snapshot["diwan"]["qasidas"], 95)
        self.assertEqual(snapshot["diwan"]["bayts"], 2682)
        self.assertTrue(snapshot["diwan"]["continuous_bayt_numbering"])
        self.assertEqual(snapshot["diwan"]["malformed_stable_ids"], 0)
        self.assertEqual(snapshot["diwan"]["numeric_heading_rewrites"], 0)
        self.assertEqual(snapshot["matching_contract"]["status"], "ok")
        self.assertTrue(snapshot["matching_contract"]["whole_word_default"])
        self.assertEqual(snapshot["matching_contract"]["literal_normalization"], "safe")
        self.assertEqual(snapshot["provenance_contract"]["status"], "ok")
        self.assertEqual(snapshot["provenance_contract"]["b42_compiler"], "unverified")

    def test_hard_token_positions_preserve_authoritative_surface_text(self):
        rows = self.conn.execute(
            "SELECT t.surface_form, t.token_norm, t.char_start, t.char_end, p.text "
            "FROM tokens t JOIN pages p ON p.id=t.page_id "
            "ORDER BY t.token_id LIMIT 500"
        ).fetchall()
        self.assertEqual(len(rows), 500)
        for row in rows:
            self.assertEqual(
                row["surface_form"], row["text"][row["char_start"]:row["char_end"]]
            )
            self.assertTrue(row["token_norm"])

    def test_hard_roots_are_nullable_curated_and_versioned(self):
        total, rooted, unversioned = self.conn.execute(
            "SELECT COUNT(*), SUM(root IS NOT NULL), "
            "SUM(root IS NOT NULL AND (lemma IS NULL OR analysis_version IS NULL)) "
            "FROM tokens"
        ).fetchone()
        self.assertGreater(total, 1_000_000)
        self.assertGreater(rooted, 1_000)
        self.assertEqual(unversioned, 0)
        roots = {
            row[0] for row in self.conn.execute(
                "SELECT DISTINCT root FROM tokens WHERE root IS NOT NULL"
            )
        }
        self.assertTrue({"حفظ", "غني", "فقر"}.issubset(roots))

    def test_hard_parallel_index_is_candidate_only(self):
        count, unsafe, self_links = self.conn.execute(
            "SELECT COUNT(*), "
            "SUM(review_status <> 'unverified_candidate' OR citation_safe <> 0), "
            "SUM(source_stable_id = candidate_stable_id) "
            "FROM diwan_parallel_candidates"
        ).fetchone()
        self.assertGreater(count, 0)
        self.assertEqual(unsafe, 0)
        self.assertEqual(self_links, 0)
        for row in self.conn.execute(
            "SELECT shared_roots, shared_root_count, evidence_kind "
            "FROM diwan_parallel_candidates LIMIT 100"
        ):
            roots = json.loads(row["shared_roots"])
            self.assertTrue(roots)
            self.assertEqual(len(roots), row["shared_root_count"])
            self.assertEqual(row["evidence_kind"], "shared_rare_curated_roots")

    def test_hard_parallel_references_resolve_to_stable_bayts(self):
        missing = self.conn.execute(
            "SELECT COUNT(*) FROM diwan_parallel_candidates d "
            "LEFT JOIN bayts a ON a.stable_id=d.source_stable_id "
            "LEFT JOIN bayts b ON b.stable_id=d.candidate_stable_id "
            "WHERE a.stable_id IS NULL OR b.stable_id IS NULL"
        ).fetchone()[0]
        self.assertEqual(missing, 0)


if __name__ == "__main__":
    unittest.main()
