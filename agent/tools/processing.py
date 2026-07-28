from agent.tools.base import Tool, ToolResult, _dedup_by_title


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
        unique, removed = _dedup_by_title(papers)
        return ToolResult(success=True, data={"papers": unique, "removed": removed})


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
        title = paper.get("title", "Untitled") or "Untitled"
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


class CompositeRanker(Tool):
    name = "composite_rank"
    description = "Rank papers by composite score: citation count, venue quality, and relevance"

    DEFAULT_WEIGHTS = {"citation": 0.4, "venue": 0.3, "relevance": 0.3}

    def execute(self, params: dict) -> ToolResult:
        papers = list(params.get("papers", []))
        weights = params.get("weights", dict(self.DEFAULT_WEIGHTS))

        if not papers:
            return ToolResult(success=True, data={"papers": []})

        # Normalize citation count (0-1)
        max_citations = max(p.get("citation_count", 0) or 0 for p in papers)
        if max_citations == 0:
            max_citations = 1  # Avoid division by zero

        for p in papers:
            # Citation score (normalized)
            cite_score = (p.get("citation_count", 0) or 0) / max_citations

            # Venue bonus
            is_top = p.get("is_top_venue", False)
            venue = p.get("venue", "") or ""
            if is_top:
                venue_score = 1.0
            elif venue:
                venue_score = 0.3  # Has venue but not top-tier
            else:
                venue_score = 0.0

            # Relevance score (normalized from 1-5 scale to 0-1)
            raw_rel = p.get("_relevance_score", 3.0) or 3.0
            rel_score = raw_rel / 5.0

            # Composite
            composite = (
                weights.get("citation", 0.4) * cite_score
                + weights.get("venue", 0.3) * venue_score
                + weights.get("relevance", 0.3) * rel_score
            )
            p["_composite_score"] = round(composite, 4)

        papers.sort(key=lambda p: p.get("_composite_score", 0), reverse=True)
        return ToolResult(success=True, data={"papers": papers})
