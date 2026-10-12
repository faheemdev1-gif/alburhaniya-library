"""Reproductions from the 2.10.11 external spot audit."""
from app.core import result_cache
from app.mcp_server import search_library
from app.services import library_db as db
from app.services.query_language import subject_phrase


def search(query):
    result_cache.clear()
    return search_library(query=query, limit=5, detail="full")


def ids(response):
    return [(row["book_id"], row["seq"]) for row in response["results"]]


def test_attested_role_phrase_survives_question_frame():
    response=search("ما صفات المريد الصادق")
    assert subject_phrase("ما صفات المريد الصادق")=="المريد الصادق"
    assert ("b07",138) in ids(response) and ("b16",37) in ids(response)
    assert response["completion"]=="full" and response["reformulation_status"]=="ok"


def test_attested_synonyms_recover_source_passages():
    assert ("b37",156) in ids(search("كيف يكون العبد بين الخشية والأمل"))
    response=search("ما فضل محبة سيدنا محمد صلى الله عليه وسلم")
    assert ("b12",174) in ids(response)
    assert response["reformulation_status"]=="ok"


def test_weak_answer_is_not_pipeline_degradation():
    response=search("كيف أربي أبنائي تربية صالحة")
    assert response["completion"]=="full" and response["stages_skipped"]==[]
    assert response["evidence_strength"]=="weak"
    assert response["reformulation_status"]=="ok"
    assert response["fewer_than_limit_reason"]=="only_n_passages_met_threshold"


def test_relation_guard_and_explicit_preparation():
    story=search("مجالسة الصالحين في تزكية النفس")
    assert all((r["book_id"],r["seq"])!=("b01",126) or r["question_relevance"]!="relation_candidate" for r in story["results"])
    death=search("كيف يستعد الإنسان للموت")
    assert ("b01",141) in ids(death)
    assert next(r for r in death["results"] if (r["book_id"],r["seq"])==("b01",141))["question_relevance"]=="relation_candidate"


def test_lexeme_root_and_orthography_safety():
    hits=db.search(query="وسواس",search_mode="lexeme",limit=200,diversify_books=False)
    assert not {("b13",147),("b01",177)} & {(r["book_id"],r["seq"]) for r in hits}
    assert "بصدقه" not in db._lexeme_index_forms("الصدقة")
    assert db.search(query="طمأنينة",search_mode="lexeme",limit=1)


def test_heading_section_and_dialogue_speaker():
    heading=db.get_passage_by_match_id("b37-p156-c494",context_mode="paragraph")
    assert "الأول:" in heading["passage"] and "الرابع:" in heading["passage"]
    assert "(4) الناس بين العلم" not in heading["passage"]
    dialogue=db.get_passage_by_match_id("b29-p23-c40",context_mode="paragraph")
    assert dialogue["speaker"]=="mixed"
    assert any(s["speaker"]=="مولانا الشيخ" and s["role"]=="answer" for s in dialogue["speaker_segments"])
