import os
import sys
import types
import unittest
import json
import re

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
from app.core.text_format import repair_quran_display_brackets


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
            self.assertIn("rank", hit)
            self.assertIn("score_kind", hit)

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

    def test_counts_respect_qasida_scope(self):
        whole_book = db.count_search(["الله"], book_ids=["b14"])
        q32 = db.count_search(
            ["الله"], book_ids=["b14"], qasida_number=32,
        )
        q91 = db.count_search(
            ["الله"], book_ids=["b14"], qasida_number=91,
        )
        self.assertGreater(whole_book, 100)
        self.assertEqual((q32, q91), (1, 0))

        stats = db.search_stats(
            ["الله"], book_ids=["b14"], qasida_number=32,
        )
        self.assertEqual(stats["matching_pages"], 1)
        self.assertEqual(stats["matching_occurrences"], 1)
        self.assertEqual(stats["per_query"][0]["matching_pages"], 1)
        self.assertEqual(stats["per_query"][0]["occurrences"], 1)

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
        self.assertNotIn("match_id", passage)
        self.assertNotIn("source", passage)
        self.assertNotIn("occurrences", passage)

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
        self.assertTrue(all(0 <= row["score"] <= 1 for row in hybrid))

    def test_exact_expands_definite_article(self):
        bare = db.search_stats(["معرفة"])
        definite = db.search_stats(["المعرفة"])
        self.assertGreaterEqual(bare["matching_pages"], definite["matching_pages"])

    def test_passage_query_restores_highlighting(self):
        hit = db.search("المريد", limit=1)[0]
        passage = db.get_passage(hit["book_id"], hit["seq"], query="المريد", context_chars=300)
        self.assertIn("<mark>", passage["passage"])

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

    def test_terms_ignore_arabic_stopwords(self):
        with_stopword = db.search("الصلاة في وقتها", search_mode="all_words", limit=5)
        without_stopword = db.search("الصلاة وقتها", search_mode="all_words", limit=5)
        self.assertEqual(
            [(x["book_id"], x["seq"]) for x in with_stopword],
            [(x["book_id"], x["seq"]) for x in without_stopword],
        )

    def test_hybrid_min_score_filters(self):
        rows = db.hybrid_search(query="الصلاة في وقتها", limit=20, min_score=0.9)
        self.assertTrue(all(row["score"] >= 0.9 for row in rows))

    def test_exact_scores_are_stable_bm25_not_reciprocal_rank(self):
        truth = db.search(
            "الحقيقة", search_mode="exact_phrase", ranking="relevance",
            diversify_books=False, limit=10,
        )
        night = db.search(
            "قيام الليل", search_mode="exact_phrase", ranking="relevance",
            diversify_books=False, limit=10,
        )
        self.assertNotEqual(
            [row["score"] for row in truth], [row["score"] for row in night],
        )
        self.assertTrue(all(row["score_kind"] == "bm25_phrase" for row in truth))
        self.assertEqual([row["rank"] for row in truth], list(range(1, 11)))

    def test_exact_min_score_filters_lexical_strength_before_pagination(self):
        unfiltered = db.search(
            "المحافظة", search_mode="exact_phrase", ranking="relevance",
            diversify_books=False, limit=20,
        )
        threshold = (unfiltered[0]["score"] + unfiltered[1]["score"]) / 2
        filtered = db.search(
            "المحافظة", search_mode="exact_phrase", ranking="relevance",
            diversify_books=False, limit=20, min_score=threshold,
        )
        self.assertGreater(len(unfiltered), len(filtered))
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["match_id"], unfiltered[0]["match_id"])
        self.assertGreaterEqual(filtered[0]["score"], threshold)

    def test_exact_min_score_preserves_filtered_pagination(self):
        kwargs = dict(
            query="المحافظة", search_mode="exact_phrase", ranking="relevance",
            diversify_books=False, min_score=0.55,
        )
        first = db.search(limit=1, offset=0, **kwargs)
        second = db.search(limit=1, offset=1, **kwargs)
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertNotEqual(first[0]["match_id"], second[0]["match_id"])
        self.assertGreaterEqual(first[0]["score"], 0.55)
        self.assertGreaterEqual(second[0]["score"], 0.55)

    def test_book_order_is_unambiguous_stable_and_non_overlapping(self):
        first = db.search(
            "معرفة", ranking="book_order", diversify_books=False,
            limit=20, offset=0,
        )
        second = db.search(
            "معرفة", ranking="book_order", diversify_books=False,
            limit=20, offset=20,
        )
        first_keys = [(row["book_id"], row["seq"]) for row in first]
        second_keys = [(row["book_id"], row["seq"]) for row in second]
        self.assertEqual(first_keys, sorted(first_keys))
        self.assertFalse(set(first_keys) & set(second_keys))

    def test_lexeme_mode_recovers_affixed_hima_forms(self):
        exact = db.search_stats(["حمى"], book_ids=["b14"])
        enumerated = db.search_stats(
            ["حمى", "الحمى", "حماك", "حماه", "حماية", "حمانا"],
            operator="OR", book_ids=["b14"],
        )
        lexeme_pages = {
            (row["book_id"], row["seq"]) for row in db.search(
                "حمى", book_ids=["b14"], search_mode="lexeme",
                diversify_books=False, limit=1000,
            )
        }
        self.assertGreaterEqual(exact["matching_pages"], 10)
        self.assertGreaterEqual(enumerated["matching_pages"], exact["matching_pages"])
        self.assertGreaterEqual(len(lexeme_pages), enumerated["matching_pages"])

    def test_search_stats_distinguish_pages_occurrences_and_terms(self):
        stats = db.search_stats(["حمى", "الحمى"], operator="OR", book_ids=["b14"])
        self.assertGreaterEqual(stats["matching_pages"], 10)
        self.assertGreater(stats["matching_occurrences"], stats["matching_pages"])
        self.assertEqual([x["query"] for x in stats["per_query"]], ["حمى", "الحمى"])
        self.assertTrue(all("matching_pages" in x and "occurrences" in x for x in stats["per_query"]))
        self.assertEqual(stats["count_basis"], "phrase")
        self.assertTrue(stats["whole_word"])
        self.assertTrue(stats["footnotes_excluded"])

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
        self.assertIn(payload["results"][0]["blk"], {"body", "toc"})

    def test_ultra_compact_block_type_does_not_collide_with_bayt_to(self):
        rows = db.search(
            "مرتبة الإنسان الكامل", book_ids=["b12"],
            ranking="relevance", diversify_books=False, limit=10,
        )
        payload = compact_search_response(
            rows, limit=10, offset=0, has_more=False, ultra=True,
        )
        by_seq = {hit["s"]: hit for hit in payload["results"]}
        self.assertEqual(by_seq[255]["blk"], "body")
        self.assertEqual(by_seq[271]["blk"], "toc")

        qasida_rows = db.search(
            "بأحمد حيث الأحمدية يهتدي", book_ids=["b14"],
            qasida_number=91, ranking="relevance",
            diversify_books=False, limit=1,
        )
        qasida = compact_search_response(
            qasida_rows, limit=1, offset=0, has_more=False, ultra=True,
        )["results"][0]
        self.assertEqual(qasida["blk"], "body")
        self.assertIsInstance(qasida["bt"], int)

    def test_noncanonical_edition_is_explicit_and_ultra_compact_safe(self):
        phrase = "عندما كنت أحشد الأجهزة الإعلامية المحلية و العالمية"
        default_rows = db.search(
            phrase, ranking="relevance", diversify_books=False, limit=10,
        )
        self.assertTrue(any(row["book_id"] == "b37" for row in default_rows))
        self.assertFalse(any(row["book_id"] == "b38" for row in default_rows))

        edition_rows = db.search(
            phrase, book_ids=["b38"], ranking="relevance",
            diversify_books=False, limit=10,
        )
        self.assertTrue(edition_rows)
        self.assertTrue(all(row["canonical_book_id"] == "b37" for row in edition_rows))
        self.assertTrue(all(row["edition_relation"] == "duplicate_excerpt" for row in edition_rows))
        ultra = compact_search_response(
            edition_rows, limit=10, offset=0, has_more=False, ultra=True,
        )
        self.assertTrue(all(hit["canon"] == "b37" for hit in ultra["results"]))
        self.assertTrue(all(hit["er"] == "duplicate_excerpt" for hit in ultra["results"]))

    def test_ultra_compact_preserves_explicit_expansions(self):
        rows = db.search("المريد", limit=4)
        from app.services.compact_response import attach_expanded_passages
        attached = attach_expanded_passages(
            rows, expand_top=2, expand_chars=400,
            passage_loader=db.get_passage_by_match_id,
        )
        payload = compact_search_response(
            rows, limit=4, offset=0, has_more=False, ultra=True,
        )
        self.assertEqual(attached, 2)
        self.assertEqual(sum("ep" in hit for hit in payload["results"]), 2)
        self.assertTrue(all(
            hit["ep"].get("passage") or hit["ep"].get("error")
            for hit in payload["results"][:2]
        ))

    def test_persian_character_normalization(self):
        from app.core.arabic_utils import normalize_arabic
        self.assertEqual(normalize_arabic("ک ی ے"), "ك ي ي")

    def test_terms_do_not_promote_root_or_concept_relatives(self):
        rows = db.search("المحافظة الصلاة وقتها", search_mode="all_words", limit=5)
        self.assertFalse(any(
            row["book_id"] == "b39" and row["seq"] == 23 for row in rows
        ))
        expression = db._query_expression("المحافظة الصلاة وقتها", "all_words")
        self.assertNotIn('"حافظ"', expression)
        self.assertNotIn('"حفظ"', expression)
        self.assertNotIn('"وقت"', expression)

    def test_terms_expose_exact_or_normalized_match_evidence(self):
        rows = db.search("المريد الشيخ", search_mode="all_words", limit=5)
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row["match_type"], "terms")
            self.assertEqual(set(row["matched_terms"]), {"المريد", "الشيخ"})
            self.assertTrue(all(
                item["relation"] in {"exact", "normalized"}
                for item in row["matched_terms"].values()
            ))

    def test_terms_highlight_every_evidence_excerpt(self):
        rows = db.search(
            "المريد الشيخ", search_mode="all_words", ranking="relevance", limit=10,
        )
        self.assertTrue(rows)
        self.assertTrue(all("<mark>" in row["snippet"] for row in rows))
        self.assertTrue(all(row["evidence_span"]["excerpt"] == row["snippet"] for row in rows))

    def test_single_term_scores_discriminate_using_bm25(self):
        rows = db.search(
            "البصيرة", search_mode="all_words", ranking="relevance", limit=10,
        )
        self.assertGreater(len({row["score"] for row in rows}), 3)
        self.assertTrue(all(row["score_kind"] == "term_proximity_bm25" for row in rows))

    def test_scores_are_higher_is_better_in_every_relevance_mode(self):
        exact = db.search("المريد", ranking="relevance", limit=8)
        hybrid = db.hybrid_search(query="الصلاة في وقتها", limit=8)
        self.assertEqual([x["score"] for x in exact],
                         sorted((x["score"] for x in exact), reverse=True))
        self.assertEqual([x["score"] for x in hybrid],
                         sorted((x["score"] for x in hybrid), reverse=True))

    def test_primary_first_uses_bounded_authority_adjustment(self):
        rows = db.search(
            "الحقيقة", ranking="primary_first", diversify_books=False, limit=30,
        )
        rank_scores = [row["rank_score"] for row in rows]
        self.assertEqual(rank_scores, sorted(rank_scores, reverse=True))
        self.assertTrue(all(
            row["rank_score"] == db.authority_adjusted_score(
                row["score"], row["source_code"], row["source_tier"],
            )
            for row in rows
        ))

        # Authority is bounded: strong secondary evidence may outrank a much
        # weaker primary mention, so provenance never hides a relevance gap.
        mixed = db.search(
            "حافظوا على الصلوات", ranking="primary_first",
            diversify_books=False, limit=20,
        )
        strong_secondary = next(row for row in mixed if row["source_code"] == "secondary")
        weak_primary = next(
            row for row in mixed
            if row["source_code"] == "primary"
            and strong_secondary["score"] - row["score"] > 0.10
        )
        self.assertLess(mixed.index(strong_secondary), mixed.index(weak_primary))

    def test_normalized_and_surface_occurrences_are_explicit(self):
        bare = db.search_stats(["معرفة"])
        definite = db.search_stats(["المعرفة"])
        self.assertEqual(bare["normalized_occurrences"], definite["normalized_occurrences"])
        self.assertNotEqual(bare["surface_occurrences"], definite["surface_occurrences"])

    def test_complete_exact_article_page_sets_are_identical(self):
        bare = db.search(
            "معرفة", ranking="book_order", diversify_books=False, limit=1000,
        )
        definite = db.search(
            "المعرفة", ranking="book_order", diversify_books=False, limit=1000,
        )
        bare_keys = {(row["book_id"], row["seq"]) for row in bare}
        definite_keys = {(row["book_id"], row["seq"]) for row in definite}
        self.assertEqual(len(bare_keys), db.count_search(["معرفة"]))
        self.assertEqual(bare_keys, definite_keys)

    def test_hybrid_uses_real_local_match_offsets(self):
        rows = db.hybrid_search(query="المحافظة على الصلاة في وقتها", limit=5)
        self.assertTrue(rows)
        self.assertTrue(any(not row["match_id"].endswith("-c0") for row in rows))
        self.assertTrue(all(row["match_type"] == "hybrid" for row in rows))

    def test_every_retrieval_mode_localizes_and_highlights_evidence(self):
        rows = [
            db.search("الحقيقة", search_mode="exact_phrase", limit=1)[0],
            db.search("المريد الشيخ", search_mode="all_words", limit=1)[0],
            db.search("المحافظة", search_mode="lexeme", limit=1)[0],
            db.hybrid_search(query="الحقيقة المحمدية", limit=1)[0],
        ]
        for row in rows:
            self.assertGreater(row["evidence_span"]["end"], row["evidence_span"]["start"])
            self.assertEqual(
                row["match_id"].rsplit("c", 1)[1],
                str(row["evidence_span"]["start"]),
            )
            self.assertIn("<mark>", row["snippet"])

    def test_short_concept_query_recovers_relevant_prayer_evidence(self):
        rows = db.hybrid_search(query="المحافظة الصلاة وقتها", limit=5)
        self.assertGreaterEqual(len(rows), 2)
        self.assertTrue(any(
            row["book_id"] == "b44" and row["seq"] in {46, 55}
            for row in rows[:3]
        ))
        self.assertTrue(any(
            "أوقاتها" in re.sub(r"</?mark>", "", row["snippet"])
            for row in rows
        ))

    def test_hybrid_evidence_span_drives_match_id_and_passage(self):
        query = "المحافظة على الصلاة وعدم تأخيرها عن وقتها"
        row = db.hybrid_search(query=query, limit=1)[0]
        self.assertIn("evidence_span", row)
        self.assertEqual(
            row["match_id"].rsplit("c", 1)[1],
            str(row["evidence_span"]["start"]),
        )
        passage = db.get_passage_by_match_id(row["match_id"], 400)
        self.assertIn("يؤخر صلاته", passage["passage"])

    def test_hybrid_scores_are_fixed_evidence_scores_not_saturated(self):
        rows = db.hybrid_search(query="الحقيقة المحمدية", limit=10)
        self.assertGreaterEqual(len(rows), 5)
        self.assertGreater(max(row["score"] for row in rows) - min(row["score"] for row in rows), 0.02)
        self.assertLess(max(row["score"] for row in rows), 0.95)
        self.assertTrue(all(row["score_kind"] == "hybrid_evidence" for row in rows))

    def test_exact_article_variant_has_real_offset_and_visible_evidence(self):
        row = db.search("المحافظة", search_mode="exact_phrase", limit=1)[0]
        self.assertFalse(row["match_id"].endswith("-c0"))
        self.assertIn("<mark>محافظة</mark>", row["snippet"])

    def test_lexeme_root_relation_is_explicit(self):
        rows = db.search("المحافظة", search_mode="lexeme", limit=5)
        self.assertTrue(rows)
        for row in rows:
            evidence = row["matched_terms"]["المحافظة"]
            self.assertEqual(evidence["relation"], "root")
            self.assertEqual(evidence["root"], "حفظ")

    def test_terms_anchor_to_minimum_covering_span(self):
        rows = db.search("المريد الشيخ", search_mode="all_words", limit=7)
        self.assertTrue(rows)
        self.assertTrue(all(not row["match_id"].endswith("-c0") for row in rows))
        self.assertTrue(all(0 < row["score"] < 1 for row in rows))

    def test_weak_lexical_hybrid_can_return_no_answer(self):
        rows = db.hybrid_search(
            query="الصلاة خير من النوم", book_ids=["b29"], limit=5,
        )
        self.assertEqual(rows, [])

    def test_body_heading_outranks_contents_copy(self):
        rows = db.search(
            "مشروعية الذكر للنساء", book_ids=["b29"],
            ranking="relevance", limit=5, diversify_books=False,
        )
        self.assertGreaterEqual(len(rows), 2)
        self.assertEqual(rows[0]["seq"], 21)
        toc = next(row for row in rows if row["seq"] == 2)
        self.assertEqual(toc["block_type"], "toc")
        self.assertLess(toc["score"], rows[0]["score"])

    def test_exact_bayt_number_and_stable_id(self):
        rows = db.search(
            "فَمَا طَلَعَتْ إِلَّا وَغَابَ ضِيَاؤُهَا",
            book_ids=["b14"], qasida_number=91, limit=3,
        )
        self.assertTrue(rows)
        self.assertEqual(rows[0]["bayt_number"], 9)
        self.assertEqual(rows[0]["stable_id"], "b14-q091-b009")
        self.assertEqual(rows[0]["container_id"], "b14-q091")

    def test_qasida_heading_has_stable_container_identity(self):
        rows = db.search(
            "كم لي على أهل الحقيقة من يد", book_ids=["b14"],
            qasida_number=6, limit=1,
        )
        self.assertTrue(rows)
        self.assertEqual(rows[0]["container_id"], "b14-q006")

    def test_diwan_structure_and_qasida_scope(self):
        page = db.get_page("b14", 44)
        self.assertEqual(page["qasida_number"], 3)
        self.assertIsNotNone(page["qasida_title"])
        self.assertLess(len(page["qasida_title"]), 200)
        self.assertIsNotNone(page["bayt_from"])
        rows = db.search("الله", book_ids=["b14"], qasida_number=3, limit=3)
        self.assertTrue(rows)
        self.assertTrue(all(row["qasida_number"] == 3 for row in rows))

        compact = compact_search_response(
            rows, limit=3, offset=0, has_more=False
        )
        for hit in compact["results"]:
            self.assertEqual(hit["qasida_number"], 3)
            self.assertIsNotNone(hit["qasida_title"])
            self.assertIsNotNone(hit["bayt_from"])
            self.assertIsNotNone(hit["bayt_to"])

        ultra = compact_search_response(
            rows, limit=3, offset=0, has_more=False, ultra=True
        )
        for hit in ultra["results"]:
            self.assertEqual(hit["q"], 3)
            self.assertIn("qt", hit)
            self.assertIn("bf", hit)
            self.assertIn("bt", hit)

    def test_whole_word_short_terms_never_highlight_substrings(self):
        sir = db.search(
            "سر", book_ids=["b13"], page_from=97, page_to=97,
            diversify_books=False, limit=10,
        )[0]
        self.assertIn("<mark>سر</mark>", sir["snippet"])
        self.assertNotIn("الي<mark>سر</mark>ى", sir["snippet"])
        self.assertEqual(sir["occurrences"], 1)

        la = db.search(
            "لا", book_ids=["b14"], page_from=246, page_to=246,
            diversify_books=False, limit=10,
        )[0]
        self.assertNotIn("ا<mark>لأ</mark>", la["snippet"])
        self.assertEqual(la["matched_terms"]["لا"]["surface_form"], "لاَ")

    def test_safe_normalization_preserves_hamza_ya_and_ta_marbuta(self):
        from app.core.arabic_utils import normalize_search_text
        self.assertNotEqual(
            normalize_search_text("جَنِيَّة", level="safe"),
            normalize_search_text("جنيه", level="safe"),
        )
        self.assertNotEqual(
            normalize_search_text("لا", level="safe"),
            normalize_search_text("لأ", level="safe"),
        )
        self.assertNotEqual(
            normalize_search_text("على", level="safe"),
            normalize_search_text("علي", level="safe"),
        )

    def test_counts_are_mode_independent_and_basis_is_explicit(self):
        exact = db.search_stats(
            ["الحقيقة المحمدية"], search_mode="exact_phrase",
            count_basis="phrase",
        )
        terms = db.search_stats(
            ["الحقيقة المحمدية"], search_mode="all_words",
            count_basis="phrase",
        )
        self.assertEqual(
            (exact["matching_pages"], exact["matching_occurrences"]),
            (terms["matching_pages"], terms["matching_occurrences"]),
        )
        self.assertEqual(exact["count_basis"], "phrase")
        term_bag = db.search_stats(
            ["الحقيقة المحمدية"], count_basis="term_bag",
        )
        self.assertEqual(term_bag["count_basis"], "term_bag")
        self.assertGreaterEqual(term_bag["matching_pages"], exact["matching_pages"])

    def test_explicit_footnotes_are_not_indexed_as_authorial_body(self):
        norm = db._connection().execute(
            "SELECT norm_text FROM pages WHERE book_id='b13' AND seq=97"
        ).fetchone()[0]
        self.assertNotIn("كتب الاسم", norm)
        self.assertIn("footnote", db.get_page("b13", 97)["content_types"])

    def test_qasida_context_and_provenance_are_explicit(self):
        qasida = db.get_qasida(91)
        self.assertTrue(qasida["complete"])
        self.assertEqual(qasida["returned_bayts"], 22)
        self.assertEqual(qasida["bayts"][8]["stable_id"], "b14-q091-b009")
        self.assertEqual(qasida["prosody"]["status"], "not_curated")

        b20 = db.get_book("b20")
        self.assertEqual(b20["compiler"], "عبد الحميد بابكر")
        self.assertEqual(b20["provenance_status"], "identified_in_corpus_colophon")
        self.assertEqual(db.get_book("b42")["compiler"], None)
        self.assertIn("do_not_assume_safwat", db.get_book("b42")["provenance_status"])

    def test_min_tier_means_tiers_one_through_requested_value(self):
        rows = db.search("الله", min_tier=2, limit=100, diversify_books=False)
        self.assertTrue(rows)
        self.assertTrue(all(row["source_tier"] <= 2 for row in rows))

    def test_zero_result_diagnostics_never_claim_absence(self):
        diagnostics = db.zero_result_diagnostics(
            ["حقيقة النون وسر الإجمال"],
            attempted_modes=["exact", "terms", "hybrid"],
        )
        self.assertTrue(diagnostics["zero_result_is_not_absence_proof"])
        self.assertEqual(diagnostics["attempted_modes"], ["exact", "terms", "hybrid"])
        self.assertTrue(diagnostics["per_term"])
        self.assertIn("do not infer corpus absence", diagnostics["message"])

    def test_longest_live_page_fits_new_default_contract(self):
        page = db.get_page("b44", 12)
        self.assertGreater(len(page["text"]), 8000)
        self.assertLessEqual(len(page["text"]), 20000)

    def test_quran_bidi_brackets_are_display_only_and_repaired(self):
        source = "] آية عظيمة مباركة ["
        repaired, changed = repair_quran_display_brackets(source)
        self.assertTrue(changed)
        self.assertEqual(repaired, "﴿ آية عظيمة مباركة ﴾")
        self.assertEqual(source, "] آية عظيمة مباركة [")

    def test_parallel_candidates_are_never_claimed_as_verified(self):
        rows = db.get_parallel_candidates("b14-q001-b007", limit=5)
        self.assertTrue(rows)
        self.assertTrue(all(row["review_status"] == "unverified_candidate" for row in rows))
        self.assertTrue(all(row["citation_safe"] is False for row in rows))


if __name__ == "__main__":
    unittest.main()
