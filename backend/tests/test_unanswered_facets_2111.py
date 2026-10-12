"""Observed production misses: subject identity and incomplete answers."""
from app.core import result_cache
from app.core.arabic_utils import normalize_search_text
from app.mcp_server import search_library
from app.services import library_db as db


def fresh(query):
    result_cache.clear()
    return search_library(query=query, limit=5, detail="full")


def test_observance_question_protects_named_night_without_claiming_guidance():
    response = fresh("كيف نحيي ليلة القدر")
    assert response["query_plan"][0]["subject_phrase"] == "ليلة القدر"
    assert response["evidence_strength"] == "weak"
    assert response["unresolved_facets"] == ["observance"]
    assert response["reformulation_status"] == "ok"
    assert response["results"]
    assert all("ليله القدر" in normalize_search_text(hit["excerpt"].replace("</mark>", "").replace("<mark>", ""),level="broad")
               for hit in response["results"])
    assert (response["results"][0]["book_id"], response["results"][0]["seq"]) != ("b27", 59)


def test_merit_does_not_complete_separate_observance_clause():
    response = fresh("ما فضل ليلة القدر وكيف نحييها")
    assert response["evidence_strength"] == "partial"
    assert response["unresolved_facets"] == ["observance"]
    assert response["results"][0]["book_id"] == "b12"


def test_two_fear_hope_mentions_do_not_establish_a_preference():
    response = fresh("هل يغلب المريد الخوف أم الرجاء")
    assert response["evidence_strength"] == "weak"
    assert response["unresolved_facets"] == ["preference"]
    assert all(hit["question_relevance"] == "topic_only" for hit in response["results"])


def test_heading_citation_contains_its_section_without_next_heading():
    page = db.get_page("b37", 156)
    start = page["text"].index("الناس بين الخوف")
    heading = db.get_passage("b37", 156, match_start=start, context_mode="paragraph")
    assert "الترهيب و الترغيب" in heading["passage"]
    assert "الأول:" in heading["passage"] and "الرابع:" in heading["passage"]
    assert "(4) الناس بين العلم" not in heading["passage"]
    assert heading["context_scope"] == "section_from_heading"
