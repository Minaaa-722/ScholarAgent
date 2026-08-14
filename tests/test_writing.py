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
    tool = WriteChapter()
    assert tool.name == "write_chapter"
    assert tool.description is not None


def test_write_chapter_execute():
    tool = WriteChapter()
    result = tool.execute({"chapter_title": "Introduction"})
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.data["chapter_title"] == "Introduction"
    assert "[Content for Introduction]" in result.data["content"]


def test_write_chapter_empty_title():
    tool = WriteChapter()
    result = tool.execute({"chapter_title": ""})
    assert result.success is True
    assert result.data["chapter_title"] == ""


def test_write_chapter_missing_title():
    tool = WriteChapter()
    result = tool.execute({})
    assert result.success is True
    assert result.data["chapter_title"] == ""


# ---------------------------------------------------------------------------
# ExpandParagraph
# ---------------------------------------------------------------------------

def test_expand_paragraph_name():
    tool = ExpandParagraph()
    assert tool.name == "expand_paragraph"
    assert tool.description is not None


def test_expand_paragraph_execute():
    tool = ExpandParagraph()
    result = tool.execute({"section": "Introduction", "paragraph_index": 2})
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.data["section"] == "Introduction"
    assert result.data["paragraph_index"] == 2
    assert "[Expanded content]" in result.data["content"]


def test_expand_paragraph_defaults():
    tool = ExpandParagraph()
    result = tool.execute({})
    assert result.success is True
    assert result.data["section"] == ""
    assert result.data["paragraph_index"] == 0


# ---------------------------------------------------------------------------
# TruncateParagraph
# ---------------------------------------------------------------------------

def test_truncate_paragraph_name():
    tool = TruncateParagraph()
    assert tool.name == "truncate_paragraph"
    assert tool.description is not None


def test_truncate_paragraph_execute():
    tool = TruncateParagraph()
    result = tool.execute({"section": "Related Work", "paragraph_index": 1})
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.data["section"] == "Related Work"
    assert result.data["paragraph_index"] == 1
    assert "[Truncated content]" in result.data["content"]


def test_truncate_paragraph_defaults():
    tool = TruncateParagraph()
    result = tool.execute({})
    assert result.success is True
    assert result.data["section"] == ""
    assert result.data["paragraph_index"] == 0


# ---------------------------------------------------------------------------
# InsertReferences
# ---------------------------------------------------------------------------

def test_insert_references_name():
    tool = InsertReferences()
    assert tool.name == "insert_references"
    assert tool.description is not None


def test_insert_references_execute():
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
    tool = InsertReferences()
    result = tool.execute({"papers": []})
    assert result.success is True
    assert result.data["references"] == []
    assert result.data["count"] == 0


def test_insert_references_missing_papers():
    tool = InsertReferences()
    result = tool.execute({})
    assert result.success is True
    assert result.data["count"] == 0
    assert result.data["references"] == []


def test_insert_references_unknown_title():
    tool = InsertReferences()
    papers = [{"no_title": True}]
    result = tool.execute({"papers": papers})
    assert result.success is True
    assert "[1] Unknown" in result.data["references"][0]