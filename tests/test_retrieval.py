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
                    "papers": [{"title": "Paper A", "authors": [], "year": 2024, "arxiv_id": "2401.00001", "source": "arxiv", "url": "", "categories": [], "citation_count": 0, "doi": "", "abstract": "A"}]
                })
            elif query.startswith("abs:"):
                return ToolResult(success=True, data={
                    "papers": [{"title": "Paper B", "authors": [], "year": 2024, "arxiv_id": "2401.00002", "source": "arxiv", "url": "", "categories": [], "citation_count": 0, "doi": "", "abstract": "B"}]
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
            paper = {"title": "Paper A", "authors": [], "year": 2024, "arxiv_id": "2401.00001", "source": "arxiv", "url": "", "categories": [], "citation_count": 0, "doi": "", "abstract": "A"}
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
            paper = {"title": "Paper A", "authors": [], "year": 2024, "arxiv_id": "2401.00001", "source": "arxiv", "url": "", "categories": [], "citation_count": 0, "doi": "", "abstract": "A"}
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
                "papers": [{"title": "New Paper", "authors": [], "year": 2024, "arxiv_id": "2401.99999", "source": "arxiv", "url": "", "categories": [], "citation_count": 0, "doi": "", "abstract": "New"}]
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
                "papers": [{"title": "Phase7 Paper", "authors": [], "year": 2024, "arxiv_id": "2401.88888", "source": "arxiv", "url": "", "categories": [], "citation_count": 0, "doi": "", "abstract": "Phase7"}]
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
                "papers": [{"title": "Duplicate Paper", "authors": [], "year": 2024, "arxiv_id": "2401.00001", "source": "arxiv", "url": "", "categories": [], "citation_count": 0, "doi": "", "abstract": "Dup"}]
            })

    mgr = FallbackManager(MockArxiv(), None, config)
    papers = [Paper(title="Duplicate Paper")]
    result = mgr.fallback_phase6(papers, "topic", ["keyword"])
    assert len(result) == 1  # dedup