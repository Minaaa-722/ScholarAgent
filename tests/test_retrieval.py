from agent.tools.retrieval import auto_quote_terms, infer_arxiv_category
from agent.core.config import SearchConfig


def test_auto_quote_terms_no_change_empty():
    assert auto_quote_terms("") == ""


def test_auto_quote_terms_no_change_single_word():
    assert auto_quote_terms("transformer") == "transformer"


def test_auto_quote_terms_no_change_already_quoted():
    assert auto_quote_terms('"hello world"') == '"hello world"'


def test_auto_quote_terms_multi_word():
    assert auto_quote_terms("hello world") == '"hello world"'


def test_auto_quote_terms_with_hyphen():
    """Fix 1: 含连字符的术语也加引号"""
    assert auto_quote_terms("vision-transformer") == '"vision-transformer"'


def test_auto_quote_terms_with_parentheses():
    """Fix 1: 含括号的术语也加引号"""
    assert auto_quote_terms("mask r-cnn") == '"mask r-cnn"'


def test_infer_arxiv_category_cv():
    config = SearchConfig()
    result = infer_arxiv_category("image segmentation", "deep learning", config.domain_cat_map)
    assert result == "cs.CV"


def test_infer_arxiv_category_nlp():
    config = SearchConfig()
    result = infer_arxiv_category("language model", "nlp", config.domain_cat_map)
    assert result == "cs.CL"


def test_infer_arxiv_category_transformer():
    """Fix 2: transformer 无固定映射，走兜底 cs.AI"""
    config = SearchConfig()
    result = infer_arxiv_category("transformer", "attention", config.domain_cat_map)
    assert result == "cs.AI"


def test_infer_arxiv_category_fallback():
    config = SearchConfig()
    result = infer_arxiv_category("quantum physics", "string theory", config.domain_cat_map)
    assert result == "cs.AI"


def test_dual_channel_arxiv_search_basic():
    from agent.tools.retrieval import dual_channel_arxiv_search, ArxivSearch
    from agent.tools.base import ToolResult
    from agent.core.config import SearchConfig

    class MockArxiv(ArxivSearch):
        def execute(self, params):
            query = params.get("query", "")
            if query.startswith("ti:"):
                return ToolResult(success=True, data={
                    "papers": [{
                        "title": "Paper A", "authors": [], "year": 2024,
                        "arxiv_id": "2401.00001", "source": "arxiv", "url": "",
                        "categories": [], "citation_count": 0, "doi": "", "abstract": "A",
                    }]
                })
            elif query.startswith("abs:"):
                return ToolResult(success=True, data={
                    "papers": [{
                        "title": "Paper B", "authors": [], "year": 2024,
                        "arxiv_id": "2401.00002", "source": "arxiv", "url": "",
                        "categories": [], "citation_count": 0, "doi": "", "abstract": "B",
                    }]
                })
            return ToolResult(success=True, data={"papers": []})

    config = SearchConfig()
    tool = MockArxiv()
    papers = dual_channel_arxiv_search(tool, "test query", "", config)
    assert len(papers) == 2
    assert papers[0].title == "Paper A"
    assert papers[1].title == "Paper B"
    assert "arxiv_ti" in papers[0].hit_channels
    assert "arxiv_abs" in papers[1].hit_channels


def test_dual_channel_arxiv_search_dedup():
    from agent.tools.retrieval import dual_channel_arxiv_search, ArxivSearch
    from agent.tools.base import ToolResult
    from agent.core.config import SearchConfig

    class MockArxiv(ArxivSearch):
        def execute(self, params):
            paper = {
                "title": "Paper A", "authors": [], "year": 2024,
                "arxiv_id": "2401.00001", "source": "arxiv", "url": "",
                "categories": [], "citation_count": 0, "doi": "", "abstract": "A",
            }
            return ToolResult(success=True, data={"papers": [paper]})

    config = SearchConfig()
    tool = MockArxiv()
    papers = dual_channel_arxiv_search(tool, "test query", "", config)
    assert len(papers) == 1  # dedup


def test_dual_channel_arxiv_search_ti_priority():
    """ti 通道的论文优先保留."""
    from agent.tools.retrieval import dual_channel_arxiv_search, ArxivSearch
    from agent.tools.base import ToolResult
    from agent.core.config import SearchConfig

    class MockArxiv(ArxivSearch):
        def execute(self, params):
            paper = {
                "title": "Paper A", "authors": [], "year": 2024,
                "arxiv_id": "2401.00001", "source": "arxiv", "url": "",
                "categories": [], "citation_count": 0, "doi": "", "abstract": "A",
            }
            return ToolResult(success=True, data={"papers": [paper]})

    config = SearchConfig()
    tool = MockArxiv()
    papers = dual_channel_arxiv_search(tool, "test query", "", config)
    # ti channel runs first, so its hit_channel is preserved
    assert papers[0].hit_channels == ["arxiv_ti"]


def test_fallback_phase6_not_triggered():
    """论文数充足时不触发 phase6."""
    from agent.tools.retrieval import FallbackManager, ArxivSearch
    from agent.tools.base import ToolResult
    from agent.tools.models import Paper

    config = SearchConfig()

    class MockArxiv(ArxivSearch):
        def execute(self, params):
            return ToolResult(success=True, data={"papers": []})

    mgr = FallbackManager(MockArxiv(), None, config)
    papers = [Paper(title=f"Paper {i}") for i in range(15)]
    result = mgr.fallback_phase6(papers, "topic", ["keyword"])
    assert len(result) == 15


def test_fallback_phase6_triggered():
    """论文数<10 时触发 phase6."""
    from agent.tools.retrieval import FallbackManager, ArxivSearch
    from agent.tools.base import ToolResult
    from agent.core.config import SearchConfig
    from agent.tools.models import Paper

    config = SearchConfig()

    class MockArxiv(ArxivSearch):
        def execute(self, params):
            return ToolResult(success=True, data={
                "papers": [{
                    "title": "New Paper", "authors": [], "year": 2024,
                    "arxiv_id": "2401.99999", "source": "arxiv", "url": "",
                    "categories": [], "citation_count": 0, "doi": "", "abstract": "New",
                }]
            })

    mgr = FallbackManager(MockArxiv(), None, config)
    papers = [Paper(title=f"Paper {i}") for i in range(3)]
    result = mgr.fallback_phase6(papers, "topic", ["keyword"])
    assert len(result) > 3


def test_fallback_phase7_single_channel():
    """Fix 4: Phase7 仅 arXiv all: 单通道."""
    from agent.tools.retrieval import FallbackManager, ArxivSearch
    from agent.tools.base import ToolResult
    from agent.core.config import SearchConfig
    from agent.tools.models import Paper

    config = SearchConfig()

    class MockArxiv(ArxivSearch):
        def execute(self, params):
            assert "ti:" not in params.get("query", "")
            assert "abs:" not in params.get("query", "")
            return ToolResult(success=True, data={
                "papers": [{
                    "title": "Phase7 Paper", "authors": [], "year": 2024,
                    "arxiv_id": "2401.88888", "source": "arxiv", "url": "",
                    "categories": [], "citation_count": 0, "doi": "", "abstract": "Phase7",
                }]
            })

    mgr = FallbackManager(MockArxiv(), None, config)
    papers = [Paper(title=f"Paper {i}") for i in range(2)]
    result = mgr.fallback_phase7(papers, "topic")
    assert len(result) == 3


def test_fallback_phase7_max_results():
    """Fix 4: Phase7 max_results 严格限制 20."""
    from agent.tools.retrieval import FallbackManager, ArxivSearch
    from agent.tools.base import ToolResult
    from agent.core.config import SearchConfig

    config = SearchConfig()
    config.fallback_phase7_max_results = 20

    class MockArxiv(ArxivSearch):
        def execute(self, params):
            assert params.get("max_results") == 20
            return ToolResult(success=True, data={"papers": []})

    mgr = FallbackManager(MockArxiv(), None, config)
    mgr.fallback_phase7([], "topic")


def test_fallback_phase7_no_ss():
    """Fix 4: Phase7 不调用 Semantic Scholar."""
    from agent.tools.retrieval import FallbackManager, ArxivSearch
    from agent.tools.base import ToolResult
    from agent.core.config import SearchConfig

    config = SearchConfig()

    class MockArxiv(ArxivSearch):
        def execute(self, params):
            return ToolResult(success=True, data={"papers": []})

    class MockSS:
        def execute(self, params):
            raise AssertionError("Phase7 should not call Semantic Scholar")

    mgr = FallbackManager(MockArxiv(), MockSS(), config)
    mgr.fallback_phase7([], "topic")


def test_fallback_phase6_dedup():
    """Phase6 合并去重."""
    from agent.tools.retrieval import FallbackManager, ArxivSearch
    from agent.tools.base import ToolResult
    from agent.core.config import SearchConfig
    from agent.tools.models import Paper

    config = SearchConfig()

    class MockArxiv(ArxivSearch):
        def execute(self, params):
            return ToolResult(success=True, data={
                "papers": [{
                    "title": "Duplicate Paper", "authors": [], "year": 2024,
                    "arxiv_id": "2401.00001", "source": "arxiv", "url": "",
                    "categories": [], "citation_count": 0, "doi": "", "abstract": "Dup",
                }]
            })

    mgr = FallbackManager(MockArxiv(), None, config)
    papers = [Paper(title="Duplicate Paper")]
    result = mgr.fallback_phase6(papers, "topic", ["keyword"])
    assert len(result) == 1  # dedup


def test_merge_results_multi_hit():
    """MergeResults 合并 hit_channels 并记录 multi_hit 日志."""
    from agent.tools.retrieval import MergeResults

    results = [
        {
            "source": "arxiv",
            "papers": [
                {"title": "Paper A", "authors": [], "year": 2024, "arxiv_id": "2401.00001",
                 "source": "arxiv", "url": "", "categories": [], "citation_count": 5,
                 "doi": "", "abstract": "Abstract A", "hit_channels": ["arxiv_ti"]},
            ],
        },
        {
            "source": "semantic_scholar",
            "papers": [
                {"title": "Paper A", "authors": [], "year": 2024, "arxiv_id": "2401.00001",
                 "source": "semantic_scholar", "url": "", "venue": "CVPR",
                 "citation_count": 10, "doi": "10.1234/paper-a",
                 "abstract": "Abstract A", "hit_channels": ["ss_query"]},
            ],
        },
    ]

    result = MergeResults().execute({"results": results})
    assert result.success
    assert result.data["total"] == 1  # deduped

    paper = result.data["papers"][0]
    # hit_channels merged
    assert set(paper["hit_channels"]) == {"arxiv_ti", "ss_query"}
    # citation_count takes max
    assert paper["citation_count"] == 10
    # venue from semantic_scholar
    assert paper["venue"] == "CVPR"
    # doi from semantic_scholar
    assert paper["doi"] == "10.1234/paper-a"
    # source becomes "merged"
    assert paper["source"] == "merged"


def test_segmented_ss_search_calls_all_segments():
    """segmented_ss_search should call SS execute for each segment."""
    from agent.tools.retrieval import segmented_ss_search
    from unittest.mock import MagicMock
    from agent.tools.base import ToolResult

    config = SearchConfig()
    ss_tool = MagicMock()
    ss_tool.execute.return_value = ToolResult(success=True, data={"papers": []})

    segmented_ss_search(ss_tool, "test query", config, "test topic")

    # Should be called 3 times (one per segment)
    assert ss_tool.execute.call_count == 3
    calls = ss_tool.execute.call_args_list
    # First call: frontier (2025-2026, min_citation=0)
    assert calls[0][0][0]["year_start"] == 2025
    assert calls[0][0][0]["min_citation_count"] == 0
    # Second call: mid (2022-2024, min_citation=3)
    assert calls[1][0][0]["year_start"] == 2022
    assert calls[1][0][0]["min_citation_count"] == 3
    # Third call: foundational (0-2021, min_citation=5)
    assert calls[2][0][0]["year_start"] == 0
    assert calls[2][0][0]["min_citation_count"] == 5


def test_segmented_ss_search_hit_channels():
    """Each segment should tag papers with appropriate hit_channel."""
    from agent.tools.retrieval import segmented_ss_search
    from unittest.mock import MagicMock
    from agent.tools.base import ToolResult

    config = SearchConfig()
    ss_tool = MagicMock()
    ss_tool.execute.side_effect = [
        ToolResult(success=True, data={"papers": [{
            "title": "Frontier Paper", "authors": [], "year": 2025, "arxiv_id": "",
            "source": "ss", "url": "", "categories": [], "citation_count": 0, "doi": "", "abstract": "test",
        }]}),
        ToolResult(success=True, data={"papers": [{
            "title": "Mid Paper", "authors": [], "year": 2023, "arxiv_id": "",
            "source": "ss", "url": "", "categories": [], "citation_count": 5, "doi": "", "abstract": "test",
        }]}),
        ToolResult(success=True, data={"papers": [{
            "title": "Classic Paper", "authors": [], "year": 2020, "arxiv_id": "",
            "source": "ss", "url": "", "categories": [], "citation_count": 10, "doi": "", "abstract": "test",
        }]}),
    ]

    result = segmented_ss_search(ss_tool, "test query", config, "test topic")
    assert len(result) == 3
    assert result[0].hit_channels == ["ss_frontier"]
    assert result[1].hit_channels == ["ss_mid"]
    assert result[2].hit_channels == ["ss_foundational"]


def test_segmented_ss_search_search_source_queries():
    """Each paper should have search_source_queries set."""
    from agent.tools.retrieval import segmented_ss_search
    from unittest.mock import MagicMock
    from agent.tools.base import ToolResult

    config = SearchConfig()
    ss_tool = MagicMock()
    ss_tool.execute.return_value = ToolResult(success=True, data={"papers": [{
        "title": "Test", "authors": [], "year": 2025, "arxiv_id": "",
        "source": "ss", "url": "", "categories": [], "citation_count": 0, "doi": "", "abstract": "test",
    }]})

    result = segmented_ss_search(ss_tool, "test query", config, "test topic")
    assert "test query" in result[0].search_source_queries


def test_fallback_phase6_has_survey_query():
    """Fallback phase6 should return papers via survey-oriented queries."""
    from agent.tools.retrieval import FallbackManager
    from unittest.mock import MagicMock
    from agent.tools.base import ToolResult

    config = SearchConfig()
    arxiv_mock = MagicMock()
    arxiv_mock.execute.return_value = ToolResult(success=True, data={"papers": [{
        "title": "Survey Result", "authors": [], "year": 2023,
        "arxiv_id": "2301.00001", "source": "arxiv", "url": "",
        "categories": [], "citation_count": 0, "doi": "", "abstract": "test",
    }]})
    mgr = FallbackManager(arxiv_mock, None, config)
    result = mgr.fallback_phase6([], "test topic", ["kw1"])
    assert len(result) >= 1
