from agent.core.config import SearchConfig


def test_search_config_defaults():
    c = SearchConfig()
    assert c.arxiv_ti_max_results == 20
    assert c.arxiv_abs_max_results == 20
    assert c.ss_max_results == 20
    assert c.rrf_enabled is True
    assert c.rrf_k == 60
    assert c.rank_alpha == 0.5
    assert c.rank_beta == 0.3
    assert c.rank_gamma == 0.2
    assert c.relevance_confidence_min == 0.6
    assert c.abstract_missing_max_confidence == 0.6
    assert c.fallback_phase6_min_papers == 10
    assert c.fallback_phase7_min_papers == 5
    assert c.fallback_phase7_max_results == 20
    assert c.domain_fallback_cat == "cs.AI"


def test_domain_cat_map_no_transformer():
    """Fix 2: transformer 已移除映射"""
    c = SearchConfig()
    assert "transformer" not in c.domain_cat_map


def test_domain_cat_map_contains_cv_keywords():
    c = SearchConfig()
    assert c.domain_cat_map["image"] == "cs.CV"
    assert c.domain_cat_map["vision"] == "cs.CV"


def test_domain_cat_map_contains_cl_keywords():
    c = SearchConfig()
    assert c.domain_cat_map["language"] == "cs.CL"
    assert c.domain_cat_map["bert"] == "cs.CL"
    assert c.domain_cat_map["llm"] == "cs.CL"


def test_search_config_custom_values():
    c = SearchConfig(arxiv_ti_max_results=10, rrf_enabled=False, rank_alpha=0.6)
    assert c.arxiv_ti_max_results == 10
    assert c.rrf_enabled is False
    assert c.rank_alpha == 0.6