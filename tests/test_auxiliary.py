"""Tests for auxiliary tools: WebSearch, CheckArxivUpdates, ShellExec.

Covers:
  - Normal execution with valid params
  - Edge cases: empty query, missing params, special characters
  - Return structure verification
"""
from agent.tools.auxiliary import WebSearch, CheckArxivUpdates, ShellExec
from agent.tools.base import ToolResult


class TestWebSearch:
    """Test WebSearch tool."""

    def test_execute_with_query(self):
        tool = WebSearch()
        result = tool.execute({"query": "transformer architecture"})
        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.data["query"] == "transformer architecture"
        assert result.data["results"] == []

    def test_execute_empty_query(self):
        tool = WebSearch()
        result = tool.execute({"query": ""})
        assert result.success is True
        assert result.data["query"] == ""

    def test_execute_missing_query(self):
        tool = WebSearch()
        result = tool.execute({})
        assert result.success is True
        assert result.data["query"] == ""

    def test_execute_special_chars(self):
        tool = WebSearch()
        result = tool.execute({"query": "test & compare <score>"})
        assert result.success is True
        assert result.data["query"] == "test & compare <score>"

    def test_tool_metadata(self):
        tool = WebSearch()
        assert tool.name == "web_search"
        assert isinstance(tool.description, str)
        assert len(tool.description) > 0


class TestCheckArxivUpdates:
    """Test CheckArxivUpdates tool."""

    def test_execute_with_topic(self):
        tool = CheckArxivUpdates()
        result = tool.execute({"topic": "vision transformer"})
        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.data["topic"] == "vision transformer"
        assert result.data["new_papers"] == []
        assert result.data["has_updates"] is False

    def test_execute_empty_topic(self):
        tool = CheckArxivUpdates()
        result = tool.execute({"topic": ""})
        assert result.success is True
        assert result.data["topic"] == ""

    def test_execute_missing_topic(self):
        tool = CheckArxivUpdates()
        result = tool.execute({})
        assert result.success is True
        assert result.data["topic"] == ""

    def test_tool_metadata(self):
        tool = CheckArxivUpdates()
        assert tool.name == "check_arxiv_updates"
        assert isinstance(tool.description, str)
        assert len(tool.description) > 0


class TestShellExec:
    """Test ShellExec tool."""

    def test_execute_with_command(self):
        tool = ShellExec()
        result = tool.execute({"command": "ls -la"})
        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.data["command"] == "ls -la"
        assert result.data["stdout"] == ""
        assert result.data["stderr"] == ""
        assert result.data["exit_code"] == 0

    def test_execute_empty_command(self):
        tool = ShellExec()
        result = tool.execute({"command": ""})
        assert result.success is True
        assert result.data["command"] == ""

    def test_execute_missing_command(self):
        tool = ShellExec()
        result = tool.execute({})
        assert result.success is True
        assert result.data["command"] == ""

    def test_tool_metadata(self):
        tool = ShellExec()
        assert tool.name == "shell_exec"
        assert isinstance(tool.description, str)
        assert len(tool.description) > 0
