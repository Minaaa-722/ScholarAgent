"""Tests for Writing tools — WriteChapter, ExpandParagraph, TruncateParagraph, InsertReferences."""
import pytest
from agent.tools.writing import (
    WriteChapter,
    ExpandParagraph,
    TruncateParagraph,
    InsertReferences,
)
from agent.tools.base import ToolResult


# ---------------------------------------------------------------------------
# WriteChapter
# ---------------------------------------------------------------------------

def test_write_chapter_name():
    """WriteChapter should have the correct name and description."""
    tool = WriteChapter()
    assert tool.name == "write_chapter"
    assert tool.description is not None


def test_write_chapter_execute():
    """WriteChapter should return ToolResult with chapter content."""
    tool = WriteChapter()
    result = tool.execute({"chapter_title": "Introduction"})
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.data["chapter_title"] == "Introduction"
    assert "[Content for Introduction]" in result.data["content"]


def test_write_chapter_empty_title():
    """WriteChapter should handle empty title gracefully."""
    tool = WriteChapter()
    result = tool.execute({"chapter_title": ""})
    assert result.success is True
    assert result.data["chapter_title"] == ""


def test_write_chapter_missing_title():
    """WriteChapter should handle missing title parameter."""
    tool = WriteChapter()
    result = tool.execute({})
    assert result.success is True
    assert result.data["chapter_title"] == ""


# ---------------------------------------------------------------------------
# ExpandParagraph
# ---------------------------------------------------------------------------

def test_expand_paragraph_name():
    """ExpandParagraph should have the correct name and description."""
    tool = ExpandParagraph()
    assert tool.name == "expand_paragraph"
    assert tool.description is not None


def test_expand_paragraph_execute():
    """ExpandParagraph should return ToolResult with expanded content."""
    tool = ExpandParagraph()
    result = tool.execute({"section": "Introduction", "paragraph_index": 2})
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.data["section"] == "Introduction"
    assert result.data["paragraph_index"] == 2
    assert "[Expanded content]" in result.data["content"]


def test_expand_paragraph_defaults():
    """ExpandParagraph should use defaults for missing params."""
    tool = ExpandParagraph()
    result = tool.execute({})
    assert result.success is True
    assert result.data["section"] == ""
    assert result.data["paragraph_index"] == 0


# ---------------------------------------------------------------------------
# TruncateParagraph
# ---------------------------------------------------------------------------

def test_truncate_paragraph_name():
    """TruncateParagraph should have the correct name and description."""
    tool = TruncateParagraph()
    assert tool.name == "truncate_paragraph"
    assert tool.description is not None


def test_truncate_paragraph_execute():
    """TruncateParagraph should return ToolResult with truncated content."""
    tool = TruncateParagraph()
    result = tool.execute({"section": "Related Work", "paragraph_index": 1})
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.data["section"] == "Related Work"
    assert result.data["paragraph_index"] == 1
    assert "[Truncated content]" in result.data["content"]


def test_truncate_paragraph_defaults():
    """TruncateParagraph should use defaults for missing params."""
    tool = TruncateParagraph()
    result = tool.execute({})
    assert result.success is True
    assert result.data["section"] == ""
    assert result.data["paragraph_index"] == 0


# ---------------------------------------------------------------------------
# InsertReferences
# ---------------------------------------------------------------------------

def test_insert_references_name():
    """InsertReferences should have the correct name and description."""
    tool = InsertReferences()
    assert tool.name == "insert_references"
    assert tool.description is not None


def test_insert_references_execute():
    """InsertReferences should format references with numbered brackets."""
    tool = InsertReferences()
    papers = [
        {"title": "Paper One"},
        {"title": "Paper Two"},
    ]
    result = tool.execute({"papers": papers})
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert len(result.data["references"]) == 2
    assert result.data["count"] == 2
    assert "[1] Paper One" in result.data["references"][0]
    assert "[2] Paper Two" in result.data["references"][1]


def test_insert_references_empty():
    """InsertReferences should handle empty paper list."""
    tool = InsertReferences()
    result = tool.execute({"papers": []})
    assert result.success is True
    assert result.data["references"] == []
    assert result.data["count"] == 0


def test_insert_references_missing_papers():
    """InsertReferences should handle missing papers parameter."""
    tool = InsertReferences()
    result = tool.execute({})
    assert result.success is True
    assert result.data["count"] == 0
    assert result.data["references"] == []


def test_insert_references_unknown_title():
    """InsertReferences should handle papers without a title key."""
    tool = InsertReferences()
    papers = [{"no_title": True}]
    result = tool.execute({"papers": papers})
    assert result.success is True
    assert "[1] Unknown" in result.data["references"][0]