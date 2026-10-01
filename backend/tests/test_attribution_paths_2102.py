"""The reported speaker must remain visible through every public read path."""
import pytest

from app.core.attribution import attribution_at
from app.mcp_server import get_page, get_passage, search_library


@pytest.mark.parametrize("mode", ["compact", "ultra_compact"])
def test_reported_view_survives_search_and_expansion(mode):
    result = search_library(query="التوسل", book_ids=["b07"],
                            page_from=256, page_to=256,
                            match_mode="exact", mode=mode)
    hit = next(h for h in result["results"] if h.get("match_id", h.get("m")) == "b07-p256-c1421")
    assert hit["reported_view"] and hit["attribution_warning"]
    expanded = get_passage(match_id=hit.get("match_id", hit.get("m")), context_mode="paragraph")
    assert expanded["reported_view"] and expanded["attribution_warning"] == hit["attribution_warning"]
    assert expanded["attribution_marker_span"]["start"] == 1382


def test_other_reported_anchor_and_full_page_guard():
    expanded = get_passage(match_id="b07-p256-c1474")
    assert expanded["reported_view"] and expanded["source_role"] == "reported_view"
    page = get_page(book_id="b07", seq=256, mode="ultra_compact")
    assert any(g["reported_view"] and g["attribution_marker_span"]["start"] == 1382
               for g in page["attribution_guards"])


def test_answer_boundary_does_not_inherit_opposing_view():
    text = "قال المعترض: موقف مخالف\nالجواب: هذا رأي آخر"
    assert attribution_at(text, text.index("مخالف"))["reported_view"]
    assert attribution_at(text, text.index("آخر"))["source_role"] == "unknown"
