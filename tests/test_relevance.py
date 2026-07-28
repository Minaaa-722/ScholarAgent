"""Tests for RelevanceFilter."""
from agent.tools.relevance import RelevanceFilter


def test_relevance_filter_parse():
    """LLM response parsing should extract scores correctly."""
    filter_tool = RelevanceFilter()
    papers = [
        {"title": "Deep Learning for CV"},
        {"title": "Database Optimization Techniques"},
    ]
    llm_response = (
        "Deep Learning for CV | 5 | Directly addresses the core topic\n"
        "Database Optimization Techniques | 2 | Tangentially related, wrong domain\n"
    )
    result = filter_tool.execute({
        "papers": papers,
        "llm_response": llm_response,
        "threshold": 3.0,
    })
    assert result.success
    kept = result.data["papers"]
    assert len(kept) == 1
    assert kept[0]["title"] == "Deep Learning for CV"
    assert kept[0]["_relevance_score"] == 5.0


def test_relevance_filter_empty_response():
    """Empty LLM response should keep all papers with neutral score."""
    filter_tool = RelevanceFilter()
    papers = [{"title": "A"}, {"title": "B"}]
    result = filter_tool.execute({
        "papers": papers,
        "llm_response": "",
        "threshold": 3.0,
    })
    assert result.success
    assert len(result.data["papers"]) == 2


def test_relevance_filter_all_below_threshold():
    """All papers below threshold should return empty list."""
    filter_tool = RelevanceFilter()
    papers = [{"title": "A"}, {"title": "B"}]
    llm_response = "A | 1 | Not relevant\nB | 2 | Marginally related\n"
    result = filter_tool.execute({
        "papers": papers,
        "llm_response": llm_response,
        "threshold": 3.0,
    })
    assert result.success
    assert len(result.data["papers"]) == 0


def test_relevance_filter_no_papers():
    result = RelevanceFilter().execute({
        "papers": [],
        "llm_response": "",
        "threshold": 3.0,
    })
    assert result.success
    assert result.data["papers"] == []


def test_relevance_filter_partial_match():
    """Some papers not in LLM response should be kept with default score."""
    filter_tool = RelevanceFilter()
    papers = [
        {"title": "A"},
        {"title": "B"},
        {"title": "C"},
    ]
    llm_response = "A | 5 | Great\nB | 2 | Poor\n"
    result = filter_tool.execute({
        "papers": papers,
        "llm_response": llm_response,
        "threshold": 3.0,
    })
    assert result.success
    # A (score 5) kept, B (score 2) filtered, C (not in response) kept with default
    assert len(result.data["papers"]) == 2
    titles = [p["title"] for p in result.data["papers"]]
    assert "A" in titles
    assert "C" in titles
    assert "B" not in titles