import os
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np


BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND_DIR)

if "app.core.config" not in sys.modules:
    config_stub = types.ModuleType("app.core.config")
    config_stub.get_settings = lambda: types.SimpleNamespace(
        library_db_path=os.path.join(BACKEND_DIR, "library.db"),
        enable_local_semantic_search=True,
        semantic_embeddings_path="semantic_embeddings.npy",
        semantic_manifest_path="semantic_manifest.json",
        semantic_min_score=0.0,
    )
    sys.modules["app.core.config"] = config_stub

from app.services.semantic_chunks import split_semantic_chunks
from app.services import semantic_search
from app.services.semantic_search import _top_indices, combine_candidates
from app.services.compact_response import compact_search_response


def _row(book_id, seq, match_type, score, tier=2, snippet="الصلاة في وقتها"):
    return {
        "book_id": book_id, "book_title": book_id, "source_grade": "أصلي",
        "source_code": "primary", "source_tier": tier, "seq": seq,
        "page_number": seq, "page_label": str(seq), "printed_page": str(seq),
        "citation_label": None, "qasida_number": None, "qasida_title": None,
        "bayt_from": None, "bayt_to": None, "snippet": snippet,
        "match_id": f"{book_id}-p{seq}-c0", "match_type": match_type,
        "score": score,
    }


class SemanticRetrievalTests(unittest.TestCase):
    def test_chunks_are_page_bounded_stable_and_overlapping(self):
        text = ("هذا نص عربي متماسك عن المحافظة على الصلاة في وقتها. " * 40).strip()
        chunks = split_semantic_chunks(text)
        self.assertGreater(len(chunks), 2)
        for chunk in chunks:
            self.assertEqual(text[chunk.start_char:chunk.end_char], chunk.text)
            self.assertLessEqual(len(chunk.text), 500)
        for previous, current in zip(chunks, chunks[1:]):
            self.assertLess(current.start_char, previous.end_char)
            self.assertGreaterEqual(previous.end_char - current.start_char, 60)
            self.assertLessEqual(previous.end_char - current.start_char, 100)

    def test_short_page_remains_one_chunk(self):
        chunks = split_semantic_chunks("نص قصير")
        self.assertEqual([(c.start_char, c.end_char, c.text) for c in chunks], [
            (0, 7, "نص قصير")
        ])

    def test_top_indices_are_descending_and_filter_safe(self):
        scores = np.array([0.1, 0.8, 0.4], dtype=np.float32)
        self.assertEqual(_top_indices(scores, 10).tolist(), [1, 2, 0])
        self.assertEqual(_top_indices(scores, 2).tolist(), [1, 2])

    def test_exact_candidate_outranks_semantic_neighbor(self):
        exact = _row("b01", 1, "exact", 1.0)
        semantic = _row("b02", 2, "semantic", 0.0, tier=1, snippet="موضوع قريب")
        semantic.update(
            semantic_score=0.95, citation_verified=False,
            verification_required=True,
        )
        rows = combine_candidates("الصلاة في وقتها", [("exact", [exact])], [semantic])
        self.assertEqual((rows[0]["book_id"], rows[0]["seq"]), ("b01", 1))

    def test_semantic_only_candidate_is_explicitly_unverified(self):
        semantic = _row("b02", 2, "semantic", 0.0)
        semantic.update(
            semantic_score=0.82, citation_verified=False,
            verification_required=True,
        )
        row = combine_candidates("معنى المريد", [], [semantic])[0]
        self.assertEqual(row["match_type"], "semantic")
        self.assertFalse(row["citation_verified"])
        self.assertTrue(row["verification_required"])

    def test_lexical_support_marks_citation_verified(self):
        lexical = _row("b01", 1, "terms", 0.8)
        semantic = _row("b01", 1, "semantic", 0.0)
        semantic.update(
            semantic_score=0.9, citation_verified=False,
            verification_required=True,
        )
        row = combine_candidates("الصلاة في وقتها", [("terms", [lexical])], [semantic])[0]
        self.assertEqual(row["match_type"], "terms")
        self.assertTrue(row["citation_verified"])
        self.assertFalse(row["verification_required"])

    def test_semantic_search_returns_required_safety_fields(self):
        metadata = [{
            "vector_index": 0, "chunk_id": "b14-p43-c10", "book_id": "b14",
            "seq": 43, "printed_page": "53", "citation_label": None,
            "qasida_number": 3, "qasida_title": "المهدية", "bayt_from": 1,
            "bayt_to": 12, "source_tier": 1, "book_title": "ديوان شراب الوصل",
            "source_grade": "أصلي", "source_code": "primary",
            "text": "نص دلالي عن الصلاة والمحافظة عليها في وقتها",
        }]
        fake_model = types.SimpleNamespace(embed_query=lambda query: [1.0, 0.0])
        with patch.object(semantic_search, "semantic_available", return_value=True), \
             patch.object(semantic_search, "_load_index", return_value=(
                 np.array([[1.0, 0.0]], dtype=np.float32),
                 {"model": "fake", "chunk_count": 1, "dimensions": 2},
             )), \
             patch.object(semantic_search, "_candidate_rows", return_value=metadata), \
             patch("app.services.embeddings.get_embedding_service", return_value=fake_model):
            row = semantic_search.semantic_search("الصلاة في وقتها", limit=1)[0]
        self.assertEqual(row["match_type"], "semantic")
        self.assertIn("semantic_score", row)
        self.assertFalse(row["citation_verified"])
        self.assertTrue(row["verification_required"])
        self.assertEqual(row["qasida_number"], 3)

        compact = compact_search_response(
            [row], limit=1, offset=0, has_more=False
        )["results"][0]
        self.assertIn("semantic_score", compact)
        self.assertFalse(compact["citation_verified"])
        self.assertTrue(compact["verification_required"])

    def test_vector_metadata_filters_book_and_qasida_before_scoring(self):
        rows = semantic_search._candidate_rows(
            book_ids=["b14"], source_code="primary",
            page_from=None, page_to=None, qasida_number=3,
        )
        self.assertTrue(rows)
        self.assertTrue(all(row["book_id"] == "b14" for row in rows))
        self.assertTrue(all(row["qasida_number"] == 3 for row in rows))
        self.assertTrue(all(row["source_code"] == "primary" for row in rows))


if __name__ == "__main__":
    unittest.main()
