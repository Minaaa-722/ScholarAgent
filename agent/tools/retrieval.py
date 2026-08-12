import logging
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Optional

from agent.tools.base import Tool, ToolResult, _dedup_by_title

logger = logging.getLogger(__name__)

ARXIV_API_URL = "http://export.arxiv.org/api/query"
SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"


# ---------------------------------------------------------------------------
# arXiv Search
# ---------------------------------------------------------------------------
class ArxivSearch(Tool):
    name = "arxiv_search"
    description = "Search arXiv for papers matching a query via the official arXiv API"

    def execute(self, params: dict) -> ToolResult:
        query = params.get("query", "").strip()
        max_results = min(params.get("max_results", 20), 100)
        year_start = params.get("year_start", 0)
        year_end = params.get("year_end", 0)
        search_field = params.get("search_field", "ti")  # ti=title, all=full text

        if not query:
            return ToolResult(success=False, error="query is required")

        # Build search query with optional filters
        # Use title-only search by default to avoid matching papers that
        # merely mention the topic in passing
        search_parts = [f"{search_field}:{urllib.parse.quote(query)}"]

        # Add arXiv category filter (cs.CV = computer vision)
        search_parts.append("cat:cs.CV")

        # Add year range filter
        if year_start and year_end:
            start_str = f"{year_start}0101"
            end_str = f"{year_end}1231"
            search_parts.append(
                f"last_updated_date:[{start_str}+TO+{end_str}]"
            )

        search_query = "+AND+".join(search_parts)

        url = (
            f"{ARXIV_API_URL}?search_query={search_query}"
            f"&max_results={max_results}&sortBy=relevance&sortOrder=descending"
        )

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ScholarAgent/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")

            papers = self._parse_arxiv_response(raw)
            logger.info("arXiv search for '%s' returned %d papers", query, len(papers))

            return ToolResult(success=True, data={
                "query": query,
                "max_results": max_results,
                "papers": papers,
                "source": "arxiv",
            })

        except Exception as e:
            logger.error("arXiv search failed: %s", e)
            return ToolResult(success=False, error=str(e))

    @staticmethod
    def _parse_arxiv_response(xml_text: str) -> list[dict]:
        """Parse arXiv Atom XML into a list of paper dicts."""
        ns = {"atom": "http://www.w3.org/2005/Atom",
              "arxiv": "http://arxiv.org/schemas/atom"}
        papers = []
        root = ET.fromstring(xml_text)

        for entry in root.findall("atom:entry", ns):
            paper_id = entry.find("atom:id", ns)
            paper_id = paper_id.text.strip() if paper_id is not None else ""

            # Extract arXiv ID from the URL
            arxiv_id = ""
            if paper_id:
                m = re.search(r"(?:arxiv\.org/abs/|arxiv\.org/)(\d+\.\d+)", paper_id)
                if m:
                    arxiv_id = m.group(1)

            title = entry.find("atom:title", ns)
            title = " ".join(title.text.strip().split()) if title is not None else ""

            summary = entry.find("atom:summary", ns)
            summary = " ".join(summary.text.strip().split()) if summary is not None else ""

            published = entry.find("atom:published", ns)
            year = int(published.text[:4]) if published is not None else 0

            authors = []
            for author_el in entry.findall("atom:author", ns):
                name_el = author_el.find("atom:name", ns)
                if name_el is not None and name_el.text:
                    authors.append(name_el.text.strip())

            categories = []
            for cat_el in entry.findall("atom:category", ns):
                term = cat_el.get("term", "")
                if term:
                    categories.append(term)

            link = ""
            for link_el in entry.findall("atom:link", ns):
                if link_el.get("title") == "pdf":
                    link = link_el.get("href", "")
                    break
            if not link:
                link = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else paper_id

            papers.append({
                "title": title,
                "authors": authors,
                "abstract": summary,
                "year": year,
                "arxiv_id": arxiv_id,
                "source": "arxiv",
                "url": link,
                "categories": categories,
                "citation_count": 0,
                "doi": "",
            })

        return papers


# ---------------------------------------------------------------------------
# Semantic Scholar Search
# ---------------------------------------------------------------------------
class SemanticScholarSearch(Tool):
    name = "semantic_scholar_search"
    description = "Search Semantic Scholar for peer-reviewed papers with citation data"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def execute(self, params: dict) -> ToolResult:
        query = params.get("query", "").strip()
        limit = min(params.get("max_results", 20), 100)
        year_start = params.get("year_start", 0)
        year_end = params.get("year_end", 0)
        min_citation_count = params.get("min_citation_count", 3)

        if not query:
            return ToolResult(success=False, error="query is required")

        headers = {"User-Agent": "ScholarAgent/1.0"}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        fields = "title,authors,year,citationCount,externalIds,venue,abstract,url"
        url = (
            f"{SEMANTIC_SCHOLAR_API_URL}?query={urllib.parse.quote(query)}"
            f"&limit={limit}&fields={fields}"
            f"&sortBy=citationCount"
            f"&fieldsOfStudy=Computer Science"
        )
        if year_start and year_end:
            url += f"&year={year_start}-{year_end}"
        if min_citation_count > 0:
            url += f"&minCitationCount={min_citation_count}"

        # Retry with backoff for rate limiting (429)
        max_attempts = 3
        data = None
        for attempt in range(1, max_attempts + 1):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json_loads(resp.read().decode("utf-8"))
                break  # success
            except Exception as e:
                if hasattr(e, "code") and e.code == 429 and attempt < max_attempts:
                    wait = 2 ** attempt
                    logger.warning(
                        "Semantic Scholar rate limited (attempt %d/%d). Waiting %ds …",
                        attempt, max_attempts, wait,
                    )
                    time.sleep(wait)
                    continue
                logger.error("Semantic Scholar search failed: %s", e)
                return ToolResult(success=False, error=str(e))

        if data is None:
            return ToolResult(success=False, error="Semantic Scholar search failed after retries")

        papers = []
        for paper in data.get("data", []):
            authors = [
                a.get("name", "") for a in paper.get("authors", [])
                if a.get("name")
            ]
            external_ids = paper.get("externalIds", {}) or {}
            papers.append({
                "title": paper.get("title", ""),
                "authors": authors,
                "abstract": paper.get("abstract", "") or "",
                "year": paper.get("year", 0) or 0,
                "arxiv_id": external_ids.get("ArXiv", ""),
                "source": "semantic_scholar",
                "url": paper.get("url", ""),
                "venue": paper.get("venue", ""),
                "citation_count": paper.get("citationCount", 0) or 0,
                "doi": external_ids.get("DOI", ""),
                "paper_id": paper.get("paperId", ""),
            })

        logger.info(
            "Semantic Scholar search for '%s' returned %d papers",
            query, len(papers),
        )
        return ToolResult(success=True, data={
            "query": query,
            "max_results": limit,
            "papers": papers,
            "source": "semantic_scholar",
        })


# ---------------------------------------------------------------------------
# Merge & Dedup
# ---------------------------------------------------------------------------
class MergeResults(Tool):
    name = "merge_results"
    description = "Merge and deduplicate papers from multiple sources by DOI/title"

    def execute(self, params: dict) -> ToolResult:
        results = params.get("results", [])
        all_papers = []
        for r in results:
            all_papers.extend(r.get("papers", []))

        # Dedup by DOI first, then by title
        seen_doi: set[str] = set()
        unique: list[dict] = []
        for p in all_papers:
            doi = (p.get("doi") or "").strip().lower()
            if doi and doi in seen_doi:
                continue
            if doi:
                seen_doi.add(doi)
            unique.append(p)

        # Secondary dedup by title for papers without DOI
        title_deduped, _ = _dedup_by_title(unique)
        # Merge metadata: prefer more complete fields
        merged = self._merge_metadata(title_deduped)

        return ToolResult(success=True, data={
            "papers": merged,
            "total": len(merged),
            "sources": list({r.get("source", "unknown") for r in results}),
        })

    @staticmethod
    def _merge_metadata(papers: list[dict]) -> list[dict]:
        """For papers appearing in both sources, merge to keep richer fields."""
        by_title: dict[str, list[dict]] = {}
        for p in papers:
            key = p.get("title", "").lower().strip()
            by_title.setdefault(key, []).append(p)

        merged = []
        for key, dups in by_title.items():
            if len(dups) == 1:
                merged.append(dups[0])
                continue
            base = dups[0].copy()
            for other in dups[1:]:
                # Prefer non-empty fields
                for field in ("abstract", "venue", "doi", "url"):
                    if not base.get(field) and other.get(field):
                        base[field] = other[field]
                # Merge authors (dedup)
                existing = set(base.get("authors", []))
                for a in other.get("authors", []):
                    if a not in existing:
                        base["authors"].append(a)
                        existing.add(a)
                # Sum citation counts
                base["citation_count"] = max(
                    base.get("citation_count", 0), other.get("citation_count", 0)
                )
                # Prefer arxiv_id from arXiv source
                if other.get("source") == "arxiv" and other.get("arxiv_id"):
                    base["arxiv_id"] = other["arxiv_id"]
                base["source"] = "merged"
            merged.append(base)

        return merged


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def json_loads(text: str):
    """Safe JSON load with error handling."""
    import json
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON response: {e}") from e