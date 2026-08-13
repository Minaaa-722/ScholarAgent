"""Integration tests for the unified paper retrieval pipeline."""
from unittest.mock import MagicMock, patch

from agent.core.pipeline import PipelineOrchestrator, TaskInfo, HarnessConfig
from agent.tools.registry import ToolRegistry
from agent.core.llm import MockLLM
from agent.guardrails.manager import GuardrailManager
from agent.tools.base import ToolResult


def _make_orch():
    """Helper: create a PipelineOrchestrator with mocked tools."""
    llm = MockLLM(fixed_response="Test response")
    tools = ToolRegistry()
    guardrails = GuardrailManager(guardrails=[])
    config = HarnessConfig()
    return PipelineOrchestrator(
        llm=llm, tools=tools, validators=[], guardrails=guardrails,
        config=config, latex_repair=None,
    )


def _make_arxiv_result(papers: list[dict]) -> ToolResult:
    return ToolResult(success=True, data={
        "query": "test", "max_results": 20, "papers": papers, "source": "arxiv",
    })


def _make_ss_result(papers: list[dict]) -> ToolResult:
    return ToolResult(success=True, data={
        "query": "test", "max_results": 20, "papers": papers, "source": "semantic_scholar",
    })


def _minimal_paper(title: str, **overrides) -> dict:
    return {
        "title": title,
        "authors": [],
        "abstract": f"Abstract for {title}",
        "year": 2024,
        "arxiv_id": "",
        "source": "arxiv",
        "url": "",
        "categories": [],
        "citation_count": 0,
        "doi": "",
        **overrides,
    }


# ---------------------------------------------------------------------------
# _retrieve_papers returns list[dict]
# ---------------------------------------------------------------------------

def test_retrieve_papers_returns_list_of_dicts():
    """_retrieve_papers 返回 list[dict]."""
    orch = _make_orch()
    orch._task = TaskInfo(topic="test topic", keywords=["test"], max_papers=50)

    # Mock the LLM to return a simple query
    with patch.object(orch.llm, "generate", return_value=MagicMock(text="transformer attention -> attention")):
        # Mock tools
        arxiv_mock = MagicMock()
        arxiv_mock.name = "arxiv_search"
        arxiv_mock.execute.return_value = _make_arxiv_result([
            _minimal_paper("Paper 1", arxiv_id="2401.00001", citation_count=5),
            _minimal_paper("Paper 2", arxiv_id="2401.00002", citation_count=3),
        ])
        orch.tools.register(arxiv_mock)

        ss_mock = MagicMock()
        ss_mock.name = "semantic_scholar_search"
        ss_mock.execute.return_value = _make_ss_result([
            _minimal_paper("Paper 3", source="semantic_scholar", citation_count=10),
        ])
        orch.tools.register(ss_mock)

        merge_mock = MagicMock()
        merge_mock.name = "merge_results"
        merge_mock.execute.side_effect = lambda params: ToolResult(
            success=True, data={"papers": params["results"][0]["papers"], "total": len(params["results"][0]["papers"])}
        )
        orch.tools.register(merge_mock)

        # Mock RelevanceFilter to keep all papers
        with patch.object(orch.llm, "generate", return_value=MagicMock(
            text='{"judgments": [{"index": 1, "title": "Paper 1", "relevance": "strong", '
            '"confidence": 0.9}, {"index": 2, "title": "Paper 2", "relevance": "weak", '
            '"confidence": 0.7}, {"index": 3, "title": "Paper 3", "relevance": "strong", '
            '"confidence": 0.95}]}'
        )):
            result = orch._retrieve_papers()

    assert isinstance(result, list)
    assert len(result) > 0
    for paper in result:
        assert isinstance(paper, dict)
        assert "title" in paper
        assert "citation_count" in paper


def test_retrieve_papers_handles_empty():
    """_retrieve_papers 在工具返回空时也能处理."""
    orch = _make_orch()
    orch._task = TaskInfo(topic="empty topic", keywords=[], max_papers=50)

    with patch.object(orch.llm, "generate", return_value=MagicMock(text="nothing -> nothing")):
        arxiv_mock = MagicMock()
        arxiv_mock.name = "arxiv_search"
        arxiv_mock.execute.return_value = _make_arxiv_result([])
        orch.tools.register(arxiv_mock)

        ss_mock = MagicMock()
        ss_mock.name = "semantic_scholar_search"
        ss_mock.execute.return_value = _make_ss_result([])
        orch.tools.register(ss_mock)

        merge_mock = MagicMock()
        merge_mock.name = "merge_results"
        merge_mock.execute.return_value = ToolResult(success=True, data={"papers": [], "total": 0})
        orch.tools.register(merge_mock)

        # Mock LLM to return empty judgments
        r = MagicMock(text='{"judgments": []}')
        with patch.object(orch.llm, "generate", return_value=r):
            result = orch._retrieve_papers()

    assert isinstance(result, list)
    # Should still return something via fallback or empty list
    # str() because the result list could be empty
    assert isinstance(result, list)


def test_retrieve_papers_fields():
    """每个返回的 dict 包含所有必要字段."""
    orch = _make_orch()
    orch._task = TaskInfo(topic="field test", keywords=["test"], max_papers=50)

    with patch.object(orch.llm, "generate", return_value=MagicMock(text="test query -> test")):
        arxiv_mock = MagicMock()
        arxiv_mock.name = "arxiv_search"
        arxiv_mock.execute.return_value = _make_arxiv_result([
            _minimal_paper("Field Test Paper", arxiv_id="2401.00010", citation_count=7, doi="10.1234/test"),
        ])
        orch.tools.register(arxiv_mock)

        ss_mock = MagicMock()
        ss_mock.name = "semantic_scholar_search"
        ss_mock.execute.return_value = _make_ss_result([])
        orch.tools.register(ss_mock)

        merge_mock = MagicMock()
        merge_mock.name = "merge_results"
        merge_mock.execute.side_effect = lambda params: ToolResult(
            success=True, data={"papers": params["results"][0]["papers"], "total": len(params["results"][0]["papers"])}
        )
        orch.tools.register(merge_mock)

        with patch.object(orch.llm, "generate", return_value=MagicMock(
            text='{"judgments": [{"index": 1, "title": "Field Test Paper", "relevance": "strong", "confidence": 0.95}]}'
        )):
            result = orch._retrieve_papers()

    assert len(result) >= 1
    paper = result[0]
    expected_fields = {
        "title", "authors", "abstract", "year", "arxiv_id",
        "source", "url", "citation_count", "doi",
    }
    assert expected_fields.issubset(paper.keys()), f"Missing fields: {expected_fields - paper.keys()}"


def test_retrieve_papers_uses_merge_results():
    """MergeResults 被正确调用（通过工具注册表）。"""
    orch = _make_orch()
    orch._task = TaskInfo(topic="merge test", keywords=["test"], max_papers=50)

    with patch.object(orch.llm, "generate", return_value=MagicMock(text="merge query -> merge")):
        arxiv_mock = MagicMock()
        arxiv_mock.name = "arxiv_search"
        arxiv_mock.execute.return_value = _make_arxiv_result([
            _minimal_paper("Merge Paper", arxiv_id="2401.00020", citation_count=5),
        ])
        orch.tools.register(arxiv_mock)

        ss_mock = MagicMock()
        ss_mock.name = "semantic_scholar_search"
        ss_mock.execute.return_value = _make_ss_result([])
        orch.tools.register(ss_mock)

        merge_called = False

        def _merge_fn(params):
            nonlocal merge_called
            merge_called = True
            assert "results" in params, "MergeResults should receive 'results' key"
            return ToolResult(success=True, data={
                "papers": params["results"][0]["papers"],
                "total": len(params["results"][0]["papers"]),
            })

        merge_mock = MagicMock()
        merge_mock.name = "merge_results"
        merge_mock.execute.side_effect = _merge_fn
        orch.tools.register(merge_mock)

        with patch.object(orch.llm, "generate", return_value=MagicMock(
            text='{"judgments": [{"index": 1, "title": "Merge Paper", "relevance": "strong", "confidence": 0.95}]}'
        )):
            orch._retrieve_papers()

    assert merge_called, "MergeResults should have been called"
