import pytest
from agent.tools.base import Tool, ToolResult
from agent.tools.registry import ToolRegistry
from agent.tools.retrieval import ArxivSearch, MergeResults
from agent.tools.processing import Dedup, SortByCitation, FormatBibtex
from agent.tools.writing import WriteChapter, InsertReferences


def test_tool_base_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Tool()


def test_tool_registry_register_and_get():
    registry = ToolRegistry()
    tool = ArxivSearch()
    registry.register(tool)
    assert registry.get("arxiv_search") is tool


def test_tool_registry_get_unknown_tool():
    registry = ToolRegistry()
    assert registry.get("nonexistent") is None


def test_tool_registry_list_tools():
    registry = ToolRegistry()
    registry.register(ArxivSearch())
    names = registry.list_tools()
    assert "arxiv_search" in names


def test_dedup_removes_duplicates():
    papers = [
        {"title": "Paper A", "source": "arxiv"},
        {"title": "Paper B", "source": "semantic_scholar"},
        {"title": "Paper A", "source": "google_scholar"},
    ]
    result = Dedup().execute({"papers": papers})
    assert len(result.data["papers"]) == 2


def test_sort_by_citation():
    papers = [
        {"title": "A", "citation_count": 5},
        {"title": "B", "citation_count": 100},
        {"title": "C", "citation_count": 20},
    ]
    result = SortByCitation().execute({"papers": papers})
    assert result.data["papers"][0]["title"] == "B"
    assert result.data["papers"][2]["title"] == "A"


def test_format_bibtex():
    paper = {
        "title": "Attention Is All You Need",
        "authors": ["Vaswani", "Shazeer"],
        "year": 2017,
        "source": "arxiv",
    }
    result = FormatBibtex().execute({"paper": paper})
    assert "@article" in result.data["bibtex"]
    assert "Attention Is All You Need" in result.data["bibtex"]


def test_format_bibtex_empty_title():
    """FormatBibtex should not crash on empty string title."""
    paper = {"title": "", "authors": ["Author"], "year": 2024}
    result = FormatBibtex().execute({"paper": paper})
    assert "@article" in result.data["bibtex"]
    assert "Untitled" in result.data["bibtex"]
