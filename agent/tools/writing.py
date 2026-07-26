from agent.tools.base import Tool, ToolResult


class WriteChapter(Tool):
    name = "write_chapter"
    description = "Write a single chapter of the survey paper"

    def execute(self, params: dict) -> ToolResult:
        chapter_title = params.get("chapter_title", "")
        return ToolResult(success=True, data={
            "chapter_title": chapter_title,
            "content": f"[Content for {chapter_title}]",
        })


class ExpandParagraph(Tool):
    name = "expand_paragraph"
    description = "Expand a specific paragraph with more detail"

    def execute(self, params: dict) -> ToolResult:
        section = params.get("section", "")
        paragraph_index = params.get("paragraph_index", 0)
        return ToolResult(success=True, data={
            "section": section,
            "paragraph_index": paragraph_index,
            "content": "[Expanded content]",
        })


class TruncateParagraph(Tool):
    name = "truncate_paragraph"
    description = "Shorten a specific paragraph"

    def execute(self, params: dict) -> ToolResult:
        section = params.get("section", "")
        paragraph_index = params.get("paragraph_index", 0)
        return ToolResult(success=True, data={
            "section": section,
            "paragraph_index": paragraph_index,
            "content": "[Truncated content]",
        })


class InsertReferences(Tool):
    name = "insert_references"
    description = "Insert reference list into the survey"

    def execute(self, params: dict) -> ToolResult:
        papers = params.get("papers", [])
        refs = []
        for i, p in enumerate(papers, 1):
            refs.append(f"[{i}] {p.get('title', 'Unknown')}")
        return ToolResult(success=True, data={
            "references": refs,
            "count": len(refs),
        })
