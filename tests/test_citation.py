"""Tests for CitationExpander."""
from agent.tools.citation import CitationExpander


def test_citation_expander_select_top_k():
    """Should select top-k papers by citation count for expansion."""
    expander = CitationExpander()
    papers = [
        {"title": "A", "citation_count": 100, "paper_id": "id1"},
        {"title": "B", "citation_count": 50,  "paper_id": "id2"},
        {"title": "C", "citation_count": 10,  "paper_id": "id3"},
    ]
    selected = expander._select_top_k(papers, top_k=2)
    assert len(selected) == 2
    assert selected[0]["title"] == "A"
    assert selected[1]["title"] == "B"


def test_citation_expander_select_top_k_with_relevance():
    """When _relevance_score is available, weight by citation + relevance."""
    expander = CitationExpander()
    papers = [
        {"title": "A", "citation_count": 100, "paper_id": "id1", "_relevance_score": 5.0},
        {"title": "B", "citation_count": 50,  "paper_id": "id2", "_relevance_score": 5.0},
        {"title": "C", "citation_count": 80,  "paper_id": "id3", "_relevance_score": 1.0},
    ]
    selected = expander._select_top_k(papers, top_k=2)
    assert selected[0]["title"] == "A"
    assert selected[1]["title"] == "B"


def test_citation_expander_empty():
    expander = CitationExpander()
    result = expander.execute({"papers": []})
    assert result.success
    assert result.data["papers"] == []


def test_citation_expander_no_paper_id():
    """Papers without paper_id should return empty (no API calls possible)."""
    expander = CitationExpander()
    papers = [{"title": "A", "citation_count": 100}]
    result = expander.execute({"papers": papers, "top_k": 5, "per_paper": 10})
    assert result.success
    assert result.data["papers"] == []
    assert result.data["expanded_from_count"] == 0