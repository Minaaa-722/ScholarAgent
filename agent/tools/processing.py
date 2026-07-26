from agent.tools.base import Tool, ToolResult


class PdfDownload(Tool):
    name = "pdf_download"
    description = "Download paper PDF from URL"

    def execute(self, params: dict) -> ToolResult:
        url = params.get("url", "")
        save_path = params.get("save_path", "")
        return ToolResult(success=True, data={
            "url": url,
            "save_path": save_path,
            "downloaded": True,
        })


class PdfParse(Tool):
    name = "pdf_parse"
    description = "Parse PDF to extract full text"

    def execute(self, params: dict) -> ToolResult:
        pdf_path = params.get("pdf_path", "")
        return ToolResult(success=True, data={
            "pdf_path": pdf_path,
            "full_text": "[Parsed text placeholder]",
            "page_count": 0,
        })


class Dedup(Tool):
    name = "dedup_papers"
    description = "Remove duplicate papers by title"

    def execute(self, params: dict) -> ToolResult:
        papers = params.get("papers", [])
        seen = set()
        unique = []
        for p in papers:
            title = p.get("title", "").lower().strip()
            if title and title not in seen:
                seen.add(title)
                unique.append(p)
        return ToolResult(success=True, data={"papers": unique, "removed": len(papers) - len(unique)})


class SortByCitation(Tool):
    name = "sort_by_citation"
    description = "Sort papers by citation count descending"

    def execute(self, params: dict) -> ToolResult:
        papers = list(params.get("papers", []))
        papers.sort(key=lambda p: p.get("citation_count", 0), reverse=True)
        return ToolResult(success=True, data={"papers": papers})


class FormatBibtex(Tool):
    name = "format_bibtex"
    description = "Generate CVPR-standard BibTeX citation"

    def execute(self, params: dict) -> ToolResult:
        paper = params.get("paper", {})
        title = paper.get("title", "Untitled")
        authors = paper.get("authors", [])
        year = paper.get("year", 2024)
        key = title.split()[0].lower() + str(year)
        author_str = " and ".join(authors) if authors else "Unknown"
        bibtex = (
            f"@article{{{key},\n"
            f"  title={{{title}}},\n"
            f"  author={{{author_str}}},\n"
            f"  year={{{year}}},\n"
            f"}}"
        )
        return ToolResult(success=True, data={"bibtex": bibtex})