"""Tests for CompositeRanker and other processing tools."""
from agent.tools.processing import CompositeRanker


def test_composite_rank_basic():
    ranker = CompositeRanker()
    papers = [
        {"title": "A", "citation_count": 100, "_relevance_score": 5.0, "is_top_venue": True},
        {"title": "B", "citation_count": 50,  "_relevance_score": 3.0, "is_top_venue": False},
        {"title": "C", "citation_count": 10,  "_relevance_score": 4.0, "is_top_venue": True},
    ]
    result = ranker.execute({"papers": papers})
    assert result.success
    ranked = result.data["papers"]
    assert ranked[0]["title"] == "A"
    assert "_composite_score" in ranked[0]


def test_composite_rank_missing_fields():
    """Papers missing some fields should still rank (graceful default)."""
    ranker = CompositeRanker()
    papers = [
        {"title": "A", "citation_count": 100},
        {"title": "B", "citation_count": 0},
    ]
    result = ranker.execute({"papers": papers})
    assert result.success
    assert len(result.data["papers"]) == 2


def test_composite_rank_empty():
    ranker = CompositeRanker()
    result = ranker.execute({"papers": []})
    assert result.success
    assert result.data["papers"] == []


def test_composite_rank_weights_config():
    """Custom weights should be accepted."""
    ranker = CompositeRanker()
    papers = [{"title": "A", "citation_count": 10, "_relevance_score": 5.0}]
    result = ranker.execute({"papers": papers, "weights": {"citation": 1.0, "venue": 0.0, "relevance": 0.0}})
    assert result.success