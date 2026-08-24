import hashlib
import os
import re
import sys
import types
import unittest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND_DIR)

config_stub = types.ModuleType("app.core.config")
config_stub.get_settings = lambda: types.SimpleNamespace(
    library_db_path=os.path.join(BACKEND_DIR, "library.db"),
    hybrid_min_relevance=0.55,
)
sys.modules.setdefault("app.core.config", config_stub)

from app.services import library_db as db
from app.services.compact_response import attach_expanded_passages
from scripts.build_index import (
    _DIWAN_ORDINAL_DIGEST,
    _QASIDA_HEADING,
    validate_diwan_structure,
)


class FinalRegressionGates(unittest.TestCase):
    def test_hard_s1_score_vectors_are_query_dependent(self):
        prayer = db.search(
            "حافظوا على الصلوات", ranking="relevance",
            diversify_books=False, limit=5,
        )
        night = db.search(
            "قيام الليل", ranking="relevance",
            diversify_books=False, limit=5,
        )
        self.assertNotEqual(
            [row["score"] for row in prayer],
            [row["score"] for row in night],
        )

    def test_hard_s2_relevance_is_strictly_descending(self):
        rows = db.search(
            "حافظوا على الصلوات", ranking="relevance",
            diversify_books=False, limit=10,
        )
        scores = [row["score"] for row in rows]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(left > right for left, right in zip(scores, scores[1:])))

    def test_hard_s3_score_kind_matches_mode(self):
        cases = [
            (db.search("الحقيقة", search_mode="exact_phrase", limit=3), "bm25_phrase"),
            (db.search("المريد الشيخ", search_mode="all_words", limit=3), "term_proximity_bm25"),
            (db.search("المحافظة", search_mode="lexeme", limit=3), "bm25_lexeme"),
            (db.hybrid_search(query="الحقيقة المحمدية", limit=3), "hybrid_evidence"),
        ]
        for rows, expected in cases:
            self.assertTrue(rows)
            self.assertTrue(all(row["score_kind"] == expected for row in rows))

    def test_hard_s4_zero_bm25_exact_hit_survives(self):
        rows = db.search(
            "الله", book_ids=["b14"], qasida_number=32,
            ranking="relevance", diversify_books=False, limit=20,
        )
        hit = next(row for row in rows if row.get("bayt_number") == 24)
        self.assertEqual(hit["score"], 0.0)
        self.assertEqual(hit["score_kind"], "bm25_phrase")

    def test_hard_n1_article_normalization_preserves_surface_counts(self):
        bare = db.search_stats(["معرفة"])
        definite = db.search_stats(["المعرفة"])
        self.assertEqual(bare["matching_pages"], 344)
        self.assertEqual(definite["matching_pages"], 344)
        self.assertEqual(bare["normalized_occurrences"], 510)
        self.assertEqual(definite["normalized_occurrences"], 510)
        self.assertEqual(bare["surface_occurrences"], 499)
        self.assertEqual(definite["surface_occurrences"], 232)

    def test_hard_n2_n4_normalized_variants_have_identical_page_counts(self):
        for left, right in (
            ("الإمام", "الامام"),
            ("الوصل", "الْوَصْل"),
            ("المعرفة", "المعرفه"),
        ):
            self.assertEqual(
                db.count_search([left]),
                db.count_search([right]),
                (left, right),
            )

    def test_hard_n5_ya_ambiguity_preserves_surface_form(self):
        rows = db.search(
            "على", book_ids=["b29"], ranking="book_order",
            diversify_books=False, limit=1000,
        )
        ambiguous = next(
            row["matched_terms"]["على"] for row in rows
            if row.get("matched_terms", {}).get("على", {}).get("surface_form") == "علي"
        )
        self.assertEqual(ambiguous["relation"], "normalized")
        self.assertIn("ى/ي", ambiguous["normalization_warning"])

        unrelated = db.search(
            "المريد", ranking="relevance", diversify_books=False, limit=20,
        )
        article_variant = next(
            evidence for row in unrelated
            for evidence in row.get("matched_terms", {}).values()
            if evidence.get("surface_form") == "مُريد"
            and evidence.get("relation") == "normalized"
        )
        self.assertNotIn("normalization_warning", article_variant)

    def test_hard_d1_d7_qasida_boundaries_and_titles(self):
        expected = {
            1: "أَنَا فِي أَنَا إِنِّي وَإِنِّيَ فِي أَنَا",
            32: "خِتَاماً بَدَأْتُ الْقَوْلَ أَنْعَتُ آيَتِي",
            55: "وَبَعْدَ الْجَمْعِ كُنَّا فِي فَنَاءٍ",
            73: "إِلَى أَجَلٍ عِنْدِي تَكُونُ عَطِيَّتِي",
            91: "بِأَحْمَدَ حَيْثُ الأَحْمَدِيَّةُ يَهْتَدِي",
            95: "كَيْفَ التَّجَلِّي وَالْهُوِيَّةُ بَلْقَعٌ",
        }
        for number, title_fragment in expected.items():
            page = db._connection().execute(
                "SELECT qasida_title FROM pages WHERE book_id='b14' "
                "AND qasida_number=? ORDER BY seq LIMIT 1", (number,),
            ).fetchone()
            self.assertIsNotNone(page)
            self.assertIn(title_fragment, page[0])
        self.assertEqual(db.search("الله", book_ids=["b14"], qasida_number=96), [])

    def test_hard_d8_d10_stable_bayt_identity(self):
        row = db.search(
            "وغاب ضياؤها", book_ids=["b14"], qasida_number=91,
            ranking="relevance", diversify_books=False, limit=1,
        )[0]
        self.assertEqual(row["bayt_number"], 9)
        self.assertEqual(row["stable_id"], "b14-q091-b009")
        self.assertEqual(row["container_id"], "b14-q091")
        self.assertRegex(row["match_id"], r"^b14-p\d+-c\d+$")
        self.assertNotEqual(row["stable_id"], row["match_id"])

    def test_hard_d9_full_diwan_sweep_and_written_ordinals(self):
        validate_diwan_structure(db._connection())
        conn = db._connection()
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM bayts WHERE book_id='b14'").fetchone()[0],
            2682,
        )
        designators = []
        for number in range(1, 96):
            text = conn.execute(
                "SELECT text FROM pages WHERE book_id='b14' AND qasida_number=? "
                "ORDER BY seq LIMIT 1", (number,),
            ).fetchone()[0]
            heading = _QASIDA_HEADING.search(text)
            self.assertIsNotNone(heading, number)
            self.assertFalse(re.fullmatch(r"[0-9٠-٩۰-۹]+", heading.group(1).strip()))
            designators.append(heading.group(1).strip())
        self.assertEqual(
            hashlib.sha256("\n".join(designators).encode()).hexdigest(),
            _DIWAN_ORDINAL_DIGEST,
        )

    def test_hard_l1_l4_terms_never_claim_root_evidence(self):
        self.assertEqual(
            db.search("المحافظة", book_ids=["b39"], search_mode="all_words", limit=5),
            [],
        )
        rows = db.search("المريد الشيخ", search_mode="all_words", limit=5)
        self.assertTrue(rows)
        for row in rows:
            self.assertTrue(row["matched_terms"])
            self.assertTrue(all(
                item["relation"] in {"exact", "normalized"}
                for item in row["matched_terms"].values()
            ))

    def test_hard_l2_lexeme_root_relation_is_explicit(self):
        rows = db.search(
            "المحافظة", book_ids=["b39"], search_mode="lexeme", limit=5,
        )
        self.assertGreaterEqual(len(rows), 3)
        for row in rows:
            evidence = row["matched_terms"]["المحافظة"]
            self.assertEqual(evidence["relation"], "root")
            self.assertEqual(evidence["root"], "حفظ")
            self.assertIn(evidence["corpus_form"], {
                "حَافِظ", "للحفظ", "لحفظ", "الحفظة", "ويحافظك", "الحفظ",
            })

    def test_quality_h1_h2_hybrid_threshold_discriminates(self):
        query = "الحقيقة المحمدية والحقيقة الأحمدية"
        broad = db.hybrid_search(query=query, min_score=0.5, limit=20, ranking="relevance")
        strict = db.hybrid_search(query=query, min_score=0.8, limit=20, ranking="relevance")
        self.assertGreaterEqual(len(broad), 5)
        self.assertLess(len(strict), len(broad))
        self.assertTrue(all(row["score"] >= 0.8 for row in strict))

    def test_quality_h3_h10_all_hybrid_traps_are_rejected(self):
        traps = (
            ("أحكام زكاة الأنعام والماشية", "b14"),
            ("الصلاة خير من النوم", "b29"),
            ("أحكام الصرف والسلم", "b14"),
            ("مواقيت الحج والإحرام", "b39"),
            ("أحكام الرضاع والحضانة", "b14"),
            ("حدود السرقة والقطع", "b26"),
            ("أنواع الربا في البيوع", "b14"),
            ("شروط صحة الوصية", "b39"),
        )
        for query, book_id in traps:
            self.assertEqual(
                db.hybrid_search(query=query, book_ids=[book_id], limit=5),
                [],
                (query, book_id),
            )

    def test_quality_h11_paraphrases_share_top_evidence(self):
        first = db.hybrid_search(
            query="المحافظة على الصلاة في وقتها", limit=3, ranking="relevance",
        )
        second = db.hybrid_search(
            query="المحافظة على الصلاة وعدم تأخيرها عن وقتها",
            limit=3, ranking="relevance",
        )
        first_keys = {(row["book_id"], row["seq"]) for row in first}
        second_keys = {(row["book_id"], row["seq"]) for row in second}
        self.assertTrue(first_keys & second_keys)

    def test_hard_h12_evidence_offsets_are_page_bounded(self):
        rows = db.hybrid_search(query="الحقيقة المحمدية", limit=8)
        self.assertTrue(rows)
        for row in rows:
            page = db.get_page(row["book_id"], row["seq"])
            span = row["evidence_span"]
            self.assertGreaterEqual(span["start"], 0)
            self.assertGreater(span["end"], span["start"])
            self.assertLessEqual(span["end"], len(page["text"]))

    def test_hard_h13_every_hybrid_hit_explains_matched_terms(self):
        rows = db.hybrid_search(
            query="الحقيقة المحمدية والحقيقة الأحمدية", limit=20,
        )
        self.assertTrue(rows)
        for row in rows:
            self.assertTrue(row.get("matched_terms"), row["match_id"])
            self.assertTrue(all(
                item.get("surface_form") and item.get("relation")
                for item in row["matched_terms"].values()
            ))

    def test_hard_f1_f2_toc_is_typed_and_downranked(self):
        rows = db.search(
            "مشروعية الذكر للنساء", book_ids=["b29"],
            ranking="relevance", diversify_books=False, limit=5,
        )
        self.assertEqual(rows[0]["block_type"], "body")
        toc = next(row for row in rows if row["block_type"] == "toc")
        self.assertLess(toc["score"], rows[0]["score"])

    def test_hard_f3_fihris_heading_phrase_is_typed_and_downranked(self):
        rows = db.search(
            "مرتبة الإنسان الكامل", book_ids=["b12"],
            ranking="relevance", diversify_books=False, limit=10,
        )
        self.assertEqual(rows[0]["seq"], 255)
        fihris = next(row for row in rows if row["seq"] == 271)
        self.assertEqual(fihris["block_type"], "toc")
        self.assertLess(fihris["score"], rows[0]["score"])

    def test_hard_d10_heading_identity_and_page_scoped_bayt_range(self):
        row = db.search(
            "بأحمد حيث الأحمدية يهتدي", book_ids=["b14"],
            qasida_number=91, ranking="relevance",
            diversify_books=False, limit=1,
        )[0]
        self.assertEqual(row["stable_id"], "b14-q091-h")
        self.assertEqual(row["stable_id_kind"], "qasida_heading")
        self.assertEqual(row["heading_id"], "b14-q091-h")
        self.assertEqual(row["qasida_bayt_count"], 22)
        self.assertEqual(row["bayt_range_scope"], "page")
        self.assertEqual((row["page_bayt_from"], row["page_bayt_to"]), (1, 12))
        self.assertNotIn("bayt_number", row)

    def test_hard_d11_diwan_printed_page_comes_from_source_footer(self):
        expected = {120: "116", 175: "171", 210: "206", 246: "242", 254: "250"}
        self.assertEqual(
            {seq: db.get_page("b14", seq)["printed_page"] for seq in expected},
            expected,
        )

    def test_hard_c1_citation_label_is_universal(self):
        for book_id, seq in (("b14", 246), ("b12", 271), ("b12", 255)):
            page = db.get_page(book_id, seq)
            self.assertTrue(page["citation_label"])
            passage = db.get_passage(book_id, seq, context_chars=250)
            self.assertEqual(passage["citation_label"], page["citation_label"])

    def test_hard_n6_article_prefix_does_not_hide_ya_warning(self):
        huda_rows = db.search(
            "هدى", ranking="relevance", diversify_books=False, limit=100,
        )
        huda = next(
            row["matched_terms"]["هدى"] for row in huda_rows
            if row.get("matched_terms", {}).get("هدى", {}).get("surface_form") == "الهدي"
        )
        self.assertIn("ى/ي", huda["normalization_warning"])

        ali_rows = db.search(
            "علي", ranking="relevance", diversify_books=False, limit=100,
        )
        ali = next(
            row["matched_terms"]["علي"] for row in ali_rows
            if row.get("matched_terms", {}).get("علي", {}).get("surface_form") == "العلى"
        )
        self.assertIn("ى/ي", ali["normalization_warning"])

    def test_hard_r1_r3_ranking_policy_is_explainable(self):
        relevance = db.search(
            "حافظوا على الصلوات", ranking="relevance",
            diversify_books=False, limit=20,
        )
        primary = db.search(
            "حافظوا على الصلوات", ranking="primary_first",
            diversify_books=False, limit=20,
        )
        self.assertEqual(
            [row["score"] for row in relevance],
            sorted((row["score"] for row in relevance), reverse=True),
        )
        self.assertEqual(
            [row["rank_score"] for row in primary],
            sorted((row["rank_score"] for row in primary), reverse=True),
        )
        self.assertEqual(db.ranking_policy("primary_first"), "authority_adjusted_relevance_v1")
        self.assertEqual(
            {(row["book_id"], row["seq"]) for row in relevance},
            {(row["book_id"], row["seq"]) for row in primary},
        )

    def test_efficiency_m1_batch_passages_are_bounded(self):
        rows = db.search("المريد", limit=2)
        passages = [db.get_passage_by_match_id(row["match_id"], 300) for row in rows]
        self.assertEqual(len(passages), 2)
        self.assertTrue(all(passage and len(passage["passage"]) <= 700 for passage in passages))

    def test_efficiency_m3_expand_top_attaches_exactly_two(self):
        rows = db.search("المريد", limit=6)
        attached = attach_expanded_passages(
            rows, expand_top=2, expand_chars=400,
            passage_loader=db.get_passage_by_match_id,
        )
        self.assertEqual(attached, 2)
        self.assertEqual(sum("expanded_passage" in row for row in rows), 2)


if __name__ == "__main__":
    unittest.main()
