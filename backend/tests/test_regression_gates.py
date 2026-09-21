import hashlib
import os
import re
import sys
import types
import unittest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND_DIR)

from app.services import library_db as db
from app.services.compact_response import attach_expanded_passages
from app.core.arabic_utils import strip_diacritics
from scripts.build_index import (
    _DIWAN_ORDINAL_DIGEST,
    _QASIDA_HEADING,
    validate_diwan_structure,
)



def with_navigation(fn):
    from functools import wraps
    from app.core.evidence_blocks import INCLUDE_TOC
    @wraps(fn)
    def wrapped(*args,**kwargs):
        token=INCLUDE_TOC.set(True)
        try:return fn(*args,**kwargs)
        finally:INCLUDE_TOC.reset(token)
    return wrapped

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

    def test_hard_s5_qasida_filtered_census_matches_filtered_results(self):
        self.assertEqual(
            db.count_search(["الله"], book_ids=["b14"], qasida_number=32),
            1,
        )
        self.assertEqual(
            db.count_search(["الله"], book_ids=["b14"], qasida_number=91),
            0,
        )

    def test_hard_n1_article_normalization_preserves_surface_counts(self):
        bare = db.search_stats(["معرفة"])
        definite = db.search_stats(["المعرفة"])
        self.assertEqual(bare["matching_pages"], definite["matching_pages"])
        self.assertEqual(
            bare["normalized_occurrences"], definite["normalized_occurrences"],
        )
        self.assertGreater(bare["surface_occurrences"], definite["surface_occurrences"])
        self.assertEqual(bare["count_basis"], "phrase")

    def test_hard_n2_n4_safe_normalization_preserves_meaningful_letters(self):
        # Tashkil remains safely ignorable.
        self.assertEqual(
            db.count_search(["الوصل"]), db.count_search(["الْوَصْل"]),
        )
        # Hamza and Ta Marbuta are not silently collapsed in literal census.
        self.assertNotEqual(
            db.count_search(["الإمام"]), db.count_search(["الامام"]),
        )
        self.assertNotEqual(
            db.count_search(["المعرفة"]), db.count_search(["المعرفه"]),
        )

    def test_hard_n5_ya_ambiguity_preserves_surface_form(self):
        rows = db.search(
            "على", book_ids=["b29"], ranking="book_order", search_mode="lexeme",
            diversify_books=False, limit=1000,
        )
        ambiguous = next(
            row["matched_terms"]["على"] for row in rows
            if row.get("matched_terms", {}).get("على", {}).get("surface_form") == "علي"
        )
        self.assertEqual(ambiguous["relation"], "broad_normalized")
        self.assertIn("surface_form is authoritative", ambiguous["normalization_warning"])

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
            self.assertIn(strip_diacritics(evidence["corpus_form"]), {
                "حافظ", "للحفظ", "لحفظ", "الحفظة", "ويحافظك", "الحفظ",
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

    @with_navigation
    def test_hard_f1_f2_toc_is_typed_and_downranked(self):
        rows = db.search(
            "مشروعية الذكر للنساء", book_ids=["b29"],
            ranking="relevance", diversify_books=False, limit=5,
        )
        self.assertEqual(rows[0]["block_type"], "body")
        toc = next(row for row in rows if row["block_type"] == "toc")
        self.assertLess(toc["score"], rows[0]["score"])

    @with_navigation
    def test_hard_f3_fihris_heading_phrase_is_typed_and_downranked(self):
        rows = db.search(
            "مرتبة الإنسان الكامل", book_ids=["b12"],
            ranking="relevance", diversify_books=False, limit=10,
        )
        self.assertEqual(rows[0]["seq"], 255)
        fihris = next(row for row in rows if row["seq"] == 271)
        self.assertEqual(fihris["block_type"], "toc")
        self.assertLess(fihris["score"], rows[0]["score"])

    def test_hard_f4_decorative_dots_do_not_hide_substantive_page(self):
        rows = db.search(
            "هدى", book_ids=["b29"], ranking="relevance", search_mode="lexeme",
            diversify_books=False, limit=10,
        )
        page = next(row for row in rows if row["seq"] == 35)
        self.assertEqual(page["block_type"], "body")
        self.assertGreater(page["score"], 0.5)

    def test_hard_f5_every_implicit_toc_is_structural_and_at_boundary(self):
        from scripts.build_index import (
            _TOC_EXPLICIT_HEADING, _TOC_MIN_ENTRY_DENSITY,
            _TOC_TRAILING_PAGE_ENTRY,
        )
        from app.core.arabic_utils import normalize_arabic

        pages = db._connection().execute(
            "SELECT p.book_id, p.seq, p.text, b.page_count "
            "FROM pages p JOIN books b USING(book_id) "
            "WHERE p.block_type='toc'"
        ).fetchall()
        self.assertTrue(pages)
        for page in pages:
            normalized = normalize_arabic(page["text"], aggressive=True)
            if _TOC_EXPLICIT_HEADING.search(normalized):
                continue
            entries = len(_TOC_TRAILING_PAGE_ENTRY.findall(page["text"]))
            self.assertGreaterEqual(entries, 2, (page["book_id"], page["seq"]))
            self.assertGreaterEqual(
                entries / max(len(page["text"]), 1),
                _TOC_MIN_ENTRY_DENSITY,
                (page["book_id"], page["seq"]),
            )
            self.assertTrue(
                page["seq"] <= 5 or page["seq"] / page["page_count"] >= 0.85,
                (page["book_id"], page["seq"]),
            )

    def test_hard_e1_duplicate_edition_is_suppressed_by_default_but_addressable(self):
        phrase = "عندما كنت أحشد الأجهزة الإعلامية المحلية و العالمية"
        default_rows = db.search(
            phrase, ranking="relevance", diversify_books=False, limit=20,
        )
        self.assertTrue(any(row["book_id"] == "b37" for row in default_rows))
        self.assertFalse(any(row["book_id"] == "b38" for row in default_rows))
        self.assertEqual(db.count_search([phrase]), 1)
        self.assertEqual(db.count_search([phrase], book_ids=["b37", "b38"]), 2)
        edition_rows = db.search(
            phrase, book_ids=["b38"], ranking="relevance",
            diversify_books=False, limit=20,
        )
        self.assertTrue(edition_rows)
        self.assertTrue(all(row["canonical_book_id"] == "b37" for row in edition_rows))
        self.assertTrue(all(not row["searchable_by_default"] for row in edition_rows))

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

    def test_hard_n6_literal_search_never_collapses_ya_or_maqsura(self):
        # Literal retrieval is deliberately stricter than the former warning-
        # only policy: distinct ى/ي forms are excluded from exact evidence and
        # census arithmetic, even when an article is attached.
        for query, forbidden in (("هدى", "الهدي"), ("علي", "العلى")):
            rows = db.search(
                query, ranking="relevance", search_mode="exact_phrase",
                diversify_books=False, limit=1000,
            )
            surfaces = {
                item.get("surface_form")
                for row in rows
                for item in row.get("matched_terms", {}).values()
            }
            self.assertNotIn(forbidden, surfaces)

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
        from app.services.compact_response import compact_search_response
        ultra = compact_search_response(
            rows, limit=6, offset=0, has_more=False, ultra=True,
        )
        self.assertEqual(sum("ep" in hit for hit in ultra["results"]), 2)
        self.assertTrue(all(
            hit.get("blk") in {"body", "toc"} for hit in ultra["results"]
        ))


if __name__ == "__main__":
    unittest.main()
