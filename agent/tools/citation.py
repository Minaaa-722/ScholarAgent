"""Citation expansion tool — expands paper pool by following citation networks."""
import logging
import time
import urllib.parse
import urllib.request

from agent.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

S2_API_BASE = "https://api.semanticscholar.org/graph/v1/paper"


class CitationExpander(Tool):
    name = "citation_expand"
    description = "Expand paper pool by fetching references and citations of seed papers"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def execute(self, params: dict) -> ToolResult:
        papers = params.get("papers", [])
        top_k = int(params.get("top_k", 5))
        per_paper = int(params.get("per_paper", 10))

        if not papers:
            return ToolResult(success=True, data={"papers": [], "expanded_from_count": 0})

        # Select top-k papers to expand from
        seeds = self._select_top_k(papers, top_k)

        # Collect seen IDs to avoid duplicates
        seen_ids = set()
        for p in papers:
            pid = p.get("paper_id", "")
            if pid:
                seen_ids.add(pid)

        expanded = []
        for seed in seeds:
            pid = seed.get("paper_id", "")
            if not pid:
                continue

            # Fetch references
            refs = self._fetch_related(pid, "references", per_paper)
            for ref_paper in refs:
                ref_id = ref_paper.get("paper_id", "")
                if ref_id and ref_id not in seen_ids:
                    seen_ids.add(ref_id)
                    ref_paper["_expanded_from"] = seed.get("title", "unknown")
                    expanded.append(ref_paper)

            # Fetch citations
            cites = self._fetch_related(pid, "citations", per_paper)
            for cite_paper in cites:
                cite_id = cite_paper.get("paper_id", "")
                if cite_id and cite_id not in seen_ids:
                    seen_ids.add(cite_id)
                    cite_paper["_expanded_from"] = seed.get("title", "unknown")
                    expanded.append(cite_paper)

            time.sleep(1.0)  # Rate limiting

        logger.info(
            "Citation expansion: %d seeds → %d expanded papers",
            len(seeds), len(expanded),
        )
        return ToolResult(success=True, data={
            "papers": expanded,
            "expanded_from_count": len(seeds),
        })

    def _select_top_k(self, papers: list[dict], top_k: int) -> list[dict]:
        """Select the top-k papers most suitable for expansion.

        Ranks by composite of citation count and relevance score.
        """
        scored = []
        for p in papers:
            citations = p.get("citation_count", 0) or 0
            relevance = p.get("_relevance_score", 3.0) or 3.0
            score = 0.5 * citations + 0.5 * relevance * 20
            scored.append((score, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:top_k] if p.get("paper_id")]

    def _fetch_related(self, paper_id: str, relation: str, limit: int) -> list[dict]:
        """Fetch references or citations of a paper from Semantic Scholar."""
        fields = "title,authors,year,citationCount,externalIds,venue,abstract"
        url = (
            f"{S2_API_BASE}/{urllib.parse.quote(paper_id)}/{relation}"
            f"?limit={limit}&fields={fields}"
        )
        headers = {"User-Agent": "ScholarAgent/1.0"}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = _json_loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning("Failed to fetch %s for %s: %s", relation, paper_id, e)
            return []

        papers = []
        for entry in data.get("data", []):
            paper_data = entry.get("citedPaper", entry.get("paper", entry))
            if not paper_data:
                continue
            authors = [
                a.get("name", "") for a in paper_data.get("authors", [])
                if a.get("name")
            ]
            external_ids = paper_data.get("externalIds", {}) or {}
            papers.append({
                "title": paper_data.get("title", ""),
                "authors": authors,
                "abstract": paper_data.get("abstract", "") or "",
                "year": paper_data.get("year", 0) or 0,
                "arxiv_id": external_ids.get("ArXiv", ""),
                "source": "semantic_scholar",
                "url": paper_data.get("url", ""),
                "venue": paper_data.get("venue", ""),
                "citation_count": paper_data.get("citationCount", 0) or 0,
                "doi": external_ids.get("DOI", ""),
                "paper_id": paper_data.get("paperId", ""),
            })

        return papers


def _json_loads(text: str):
    """Safe JSON load with error handling."""
    import json
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON response: {e}") from e