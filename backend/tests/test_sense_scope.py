from app.services.question_search import sense_conflict


def test_fixed_expression_only_excludes_its_own_evidence():
    text = "العجب كل العجب. علاج العجب التواضع."
    assert sense_conflict("ما علاج العجب", text, 0, 5)
    start = text.rindex("العجب")
    assert not sense_conflict("ما علاج العجب", text, start, start + 5)
    assert not sense_conflict("ما معنى التواضع", text, 0, 5)


def test_explicit_age_query_keeps_age_reading():
    text = "بلغ الكِبَر في السن"
    assert not sense_conflict("ما معنى الكِبَر", text, 4, 11)
    assert sense_conflict("كيف يتخلص المريد من الكِبْر", text, 4, 11)
