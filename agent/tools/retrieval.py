from agent.tools.base import Tool, ToolResult


class ArxivSearch(Tool):
    name = "arxiv_search"
    description = "Search arXiv for papers matching a query"

    def execute(self, params: dict) -> ToolResult:
        query = params.get("query", "")
        max_results = params.get("max_results", 20)
        # Real implementation would call arXiv API via arxiv library
        # For now, return mock data structure
        return ToolResult(success=True, data={
            "query": query,
            "max_results": max_results,
            "papers": [],
            "source": "arxiv",
        })


class SemanticScholarSearch(Tool):
    name = "semantic_scholar_search"
    description = "Search Semantic Scholar for peer-reviewed papers"

    def execute(self, params: dict) -> ToolResult:
        query = params.get("query", "")
        return ToolResult(success=True, data={
            "query": query,
            "papers": [],
            "source": "semantic_scholar",
        })


class GoogleScholarSearch(Tool):
    name = "google_scholar_search"
    description = "Search Google Scholar as fallback source"

    def execute(self, params: dict) -> ToolResult:
        query = params.get("query", "")
        return ToolResult(success=True, data={
            "query": query,
            "papers": [],
            "source": "google_scholar",
        })


class MergeResults(Tool):
    name = "merge_results"
    description = "Merge and deduplicate papers from multiple sources"

    def execute(self, params: dict) -> ToolResult:
        results = params.get("results", [])
        all_papers = []
        for r in results:
            all_papers.extend(r.get("papers", []))
        seen = set()
        unique = []
        for p in all_papers:
            key = p.get("title", "").lower().strip()
            if key and key not in seen:
                seen.add(key)
                unique.append(p)
        return ToolResult(success=True, data={"papers": unique, "total": len(unique)})