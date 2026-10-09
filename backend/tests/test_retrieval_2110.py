"""The answer span should outrank adjacent topic mentions in how-to searches."""

from app.core import result_cache
from app.mcp_server import search_library


def test_procedural_answer_survives_question_wording():
    for query in (
        "كيف يتوب العبد من ذنوبه وهل يقبل الله توبته",
        "كيف يتوب الإنسان إذا أذنب وهل يغفر له",
        "ما الذي يجب على التائب فعله حتى تصح توبته",
        "كيف أرجع إلى الله بعد المعصية",
    ):
        result_cache.clear()
        response = search_library(query=query, limit=5)
        assert ("b25", 137) in {
            (hit["book_id"], hit["seq"]) for hit in response["results"]
        }
        answer = next(
            hit for hit in response["results"]
            if (hit["book_id"], hit["seq"]) == ("b25", 137)
        )
        assert "شروط التوبة" in answer["excerpt"]
        assert "ثلاث" in answer["excerpt"]
        assert answer.get(
            "answer_verified", response.get("result_defaults", {}).get("answer_verified")
        ) is False


def test_passing_mention_of_conditions_does_not_displace_the_list():
    result_cache.clear()
    response = search_library(
        query="كيف يتوب العبد من ذنوبه وهل يقبل الله توبته", limit=5,
    )
    positions = {(hit["book_id"], hit["seq"]): i for i, hit in enumerate(response["results"])}
    assert positions[("b25", 137)] == 0
    assert ("b01", 159) not in positions


def test_unanswered_child_rearing_question_stays_weak():
    result_cache.clear()
    response = search_library(query="إزاي أربي ولادي تربية صالحة", limit=5)
    assert response["evidence_strength"] == "weak"
    assert all(hit["question_relevance"] == "topic_only" for hit in response["results"])
