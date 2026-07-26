from agent.tools.base import Tool, ToolResult


class WebSearch(Tool):
    name = "web_search"
    description = "Search web for niche topics"

    def execute(self, params: dict) -> ToolResult:
        query = params.get("query", "")
        return ToolResult(success=True, data={
            "query": query,
            "results": [],
        })


class CheckArxivUpdates(Tool):
    name = "check_arxiv_updates"
    description = "Check for new papers on arXiv since last check"

    def execute(self, params: dict) -> ToolResult:
        topic = params.get("topic", "")
        return ToolResult(success=True, data={
            "topic": topic,
            "new_papers": [],
            "has_updates": False,
        })


class ShellExec(Tool):
    name = "shell_exec"
    description = "Execute shell commands safely"

    def execute(self, params: dict) -> ToolResult:
        command = params.get("command", "")
        return ToolResult(success=True, data={
            "command": command,
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
        })