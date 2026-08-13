from agent.tools.models import Paper
from agent.core.config import SearchConfig
from agent.tools.processing import rank_papers


def test_rank_papers_empty():
    config = SearchConfig()
    result = rank_papers([], config)
    assert result == []


def test_rank_papers_single():
    config = SearchConfig()
    p = Paper(title="Single Paper", citation_count=10, year=2024, relevance="strong")
    result = rank_papers([p], config)
    assert len(result) == 1
    assert result[0].composite_score > 0


def test_rank_papers_citation_weight():
    config = SearchConfig()
    p1 = Paper(title="Highly Cited", citation_count=100, year=2024, relevance="strong")
    p2 = Paper(title="Low Citations", citation_count=1, year=2024, relevance="strong")
    result = rank_papers([p1, p2], config)
    assert result[0].title == "Highly Cited"
    assert result[0].composite_score > result[1].composite_score


def test_rank_papers_relevance_weight():
    config = SearchConfig()
    p1 = Paper(title="Strong Relevant", citation_count=10, year=2024, relevance="strong")
    p2 = Paper(title="Weak Relevant", citation_count=10, year=2024, relevance="weak")
    result = rank_papers([p1, p2], config)
    assert result[0].title == "Strong Relevant"


def test_rank_papers_recency_weight():
    config = SearchConfig()
    p1 = Paper(title="Recent", citation_count=10, year=2025, relevance="strong")
    p2 = Paper(title="Old", citation_count=10, year=2019, relevance="strong")
    result = rank_papers([p1, p2], config)
    assert result[0].title == "Recent"


def test_rank_papers_rrf_boost():
    """RRF 启用时，多通道论文获额外提分."""
    config = SearchConfig()
    config.rrf_enabled = True
    config.rrf_k = 60

    p1 = Paper(title="Multi Channel", citation_count=5, year=2024, relevance="weak",
               hit_channels=["arxiv_ti", "semantic_scholar"])
    p2 = Paper(title="Single Channel", citation_count=10, year=2024, relevance="strong",
               hit_channels=["arxiv_abs"])
    rank_papers([p1, p2], config)
    assert p1.composite_score > 0
    assert p2.composite_score > 0


def test_rank_papers_rrf_disabled():
    """RRF 禁用时不计算额外分."""
    config = SearchConfig()
    config.rrf_enabled = False
    p = Paper(title="Test", citation_count=10, year=2024, relevance="strong",
              hit_channels=["arxiv_ti", "arxiv_abs"])
    rank_papers([p], config)
    assert p.composite_score > 0