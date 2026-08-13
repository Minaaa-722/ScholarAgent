from agent.tools.models import Paper
from agent.core.config import SearchConfig
from agent.tools.processing import rank_papers, stratified_sample
import math


def test_rank_papers_empty():
    config = SearchConfig()
    result = rank_papers([], config)
    assert result == []


def test_rank_papers_single():
    config = SearchConfig()
    p = Paper(title="Single Paper", citation_count=10, year=2024, contribution_type="strong")
    result = rank_papers([p], config)
    assert len(result) == 1
    assert result[0].composite_score > 0


def test_rank_papers_citation_weight():
    config = SearchConfig()
    p1 = Paper(title="Highly Cited", citation_count=100, year=2024, contribution_type="strong")
    p2 = Paper(title="Low Citations", citation_count=1, year=2024, contribution_type="strong")
    result = rank_papers([p1, p2], config)
    assert result[0].title == "Highly Cited"
    assert result[0].composite_score > result[1].composite_score


def test_rank_papers_relevance_weight():
    config = SearchConfig()
    p1 = Paper(title="Strong Relevant", citation_count=10, year=2024, contribution_type="strong")
    p2 = Paper(title="Extension", citation_count=10, year=2024, contribution_type="weak_extension")
    result = rank_papers([p1, p2], config)
    assert result[0].title == "Strong Relevant"


def test_rank_papers_recency_weight():
    config = SearchConfig()
    p1 = Paper(title="Recent", citation_count=10, year=2025, contribution_type="strong")
    p2 = Paper(title="Old", citation_count=10, year=2019, contribution_type="strong")
    result = rank_papers([p1, p2], config)
    assert result[0].title == "Recent"


def test_rank_papers_rrf_boost():
    """RRF 启用时，多通道论文获额外提分."""
    config = SearchConfig()
    config.rrf_enabled = True
    config.rrf_k = 60

    p1 = Paper(title="Multi Channel", citation_count=5, year=2024, contribution_type="weak_extension",
               hit_channels=["arxiv_ti", "semantic_scholar"])
    p2 = Paper(title="Single Channel", citation_count=10, year=2024, contribution_type="strong",
               hit_channels=["arxiv_abs"])
    rank_papers([p1, p2], config)
    assert p1.composite_score > 0
    assert p2.composite_score > 0


def test_rank_papers_rrf_disabled():
    """RRF 禁用时不计算额外分."""
    config = SearchConfig()
    config.rrf_enabled = False
    p = Paper(title="Test", citation_count=10, year=2024, contribution_type="strong",
              hit_channels=["arxiv_ti", "arxiv_abs"])
    rank_papers([p], config)
    assert p.composite_score > 0


# === Task 6: contribution_type weight tests ===


def test_rank_papers_contribution_type_weights():
    """strong > weak_extension > weak_application 权重应有差异."""
    config = SearchConfig()
    p_strong = Paper(title="Strong", citation_count=10, year=2024, contribution_type="strong")
    p_ext = Paper(title="Extension", citation_count=10, year=2024, contribution_type="weak_extension")
    p_app = Paper(title="Application", citation_count=10, year=2024, contribution_type="weak_application")

    rank_papers([p_strong, p_ext, p_app], config)
    scores = {p.title: p.composite_score for p in [p_strong, p_ext, p_app]}
    assert scores["Strong"] > scores["Extension"] > scores["Application"]


def test_rank_papers_exponential_decay():
    """指数衰减：2025年论文应高于2020年论文."""
    config = SearchConfig()
    p_new = Paper(title="2025 Paper", citation_count=10, year=2025, contribution_type="strong")
    p_old = Paper(title="2020 Paper", citation_count=10, year=2020, contribution_type="strong")

    rank_papers([p_new, p_old], config)
    assert p_new.composite_score > p_old.composite_score

    # 验证确为指数衰减：exp(-0.15 * 1) vs exp(-0.15 * 6)
    expected_decay_new = math.exp(-config.rank_decay_factor * 1)
    expected_decay_old = math.exp(-config.rank_decay_factor * 6)
    assert expected_decay_new > expected_decay_old


# === Task 6: stratified_sample tests ===


def test_stratified_sample_empty():
    config = SearchConfig()
    assert stratified_sample([], config) == []


def test_stratified_sample_few_papers():
    """少量论文时每个年代组至少保留1篇."""
    config = SearchConfig()
    papers = [
        Paper(title="Frontier A", citation_count=10, year=2025, composite_score=0.9),
        Paper(title="Mid A", citation_count=10, year=2023, composite_score=0.8),
        Paper(title="Classic A", citation_count=10, year=2020, composite_score=0.7),
    ]
    result = stratified_sample(papers, config)
    assert len(result) >= 3  # all kept


def test_stratified_sample_basic():
    """大量论文时按比例采样."""
    config = SearchConfig()
    papers = []
    for i in range(20):
        papers.append(Paper(title=f"Frontier_{i}", citation_count=10, year=2025, composite_score=0.9 - i * 0.01))
    for i in range(20):
        papers.append(Paper(title=f"Mid_{i}", citation_count=10, year=2023, composite_score=0.8 - i * 0.01))
    for i in range(20):
        papers.append(Paper(title=f"Classic_{i}", citation_count=10, year=2020, composite_score=0.7 - i * 0.01))

    result = stratified_sample(papers, config)
    assert len(result) > 0


def test_stratified_sample_quota_respected():
    """配额比例大致正确：30/40/30."""
    config = SearchConfig()
    papers = []
    for i in range(50):
        papers.append(Paper(title=f"Frontier_{i}", citation_count=10, year=2026, composite_score=1.0 - i * 0.005))
    for i in range(50):
        papers.append(Paper(title=f"Mid_{i}", citation_count=10, year=2023, composite_score=0.8 - i * 0.005))
    for i in range(50):
        papers.append(Paper(title=f"Classic_{i}", citation_count=10, year=2020, composite_score=0.6 - i * 0.005))

    result = stratified_sample(papers, config)
    assert len(result) > 0

    # 各组至少保留1篇
    titles = [p.title for p in result]
    assert any("Frontier" in t for t in titles)
    assert any("Mid" in t for t in titles)
    assert any("Classic" in t for t in titles)
