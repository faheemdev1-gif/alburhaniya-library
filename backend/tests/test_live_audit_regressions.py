"""Cases derived from retrieved source pages and the deployed 2.10.0 audit."""
from app.mcp_server import search_library, get_passage, get_book
from app.services.query_language import language_plan
from app.core import result_cache


def test_comparison_finds_primary_source_and_avoids_unrelated_relief():
    result_cache.clear()
    query = "ما الفرق بين التوكل والتواكل؟"
    assert language_plan(query)["negation_present"] is False
    result = search_library(query=query, limit=8, detail="full")
    assert result["completion"] == "full"
    assert not result["stages_skipped"]
    assert (result["results"][0]["book_id"], result["results"][0]["seq"]) == ("b10", 20)
    assert all("التوكل" in hit["excerpt"] and "التواكل" in hit["excerpt"]
               for hit in result["results"])
    passage = get_passage(match_id=result["results"][0]["match_id"])
    assert "الجد والإجتهاد مع التوكل" in passage["passage"]


def test_literal_counts_exclude_article_variants():
    result = search_library(query="التوبة", match_mode="exact", book_ids=["b12"],
                            page_from=60, page_to=60, include_counts=True)
    assert result["normalized_matching_pages"] == 1
    assert result["normalized_occurrences"] == 2
    assert result["literal_matching_pages"] == result["literal_occurrences"] == 0
    assert result["results"][0]["matched_terms"]["التوبة"]["relation"] == "article_variant"


def test_etiquette_guidance_outweighs_topic_introduction():
    result = search_library(query="ما هي آداب المريد مع الشيخ؟", limit=8)
    assert (result["results"][0]["book_id"], result["results"][0]["seq"]) != ("b37", 31)
    assert (result["results"][0]["book_id"], result["results"][0]["seq"]) in {("b37",57),("b07",119)}


def test_compiler_note_consistent_and_paragraph_bounded():
    book = get_book(book_id="b37")
    assert "عبد الحميد بابكر" in book["source_note"]
    passage = get_passage(match_id="b07-p119-c182", context_mode="paragraph")
    assert len(passage["context_segments"]) <= 3
    assert passage["truncated"] and passage["context_stop_reason"] == "page_or_character_cap"
