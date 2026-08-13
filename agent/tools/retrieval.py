import logging
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Optional

from agent.tools.base import Tool, ToolResult

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

        # Add arXiv category filter for CS/AI fields
        cs_categories = ["cs.AI", "cs.LG", "cs.CV", "cs.CL", "cs.IR", "cs.NE", "cs.MA", "cs.SE", "cs.DB", "cs.CR", "cs.DC"]
        category_filter = "+OR+".join(f"cat:{cat}" for cat in cs_categories)
        search_parts.append(f"({category_filter})")

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
            f"&fieldsOfStudy={urllib.parse.quote('Computer Science')}"
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

        # Dedup by DOI first, then merge metadata for title duplicates
        seen_doi: set[str] = set()
        unique: list[dict] = []
        for p in all_papers:
            doi = (p.get("doi") or "").strip().lower()
            if doi and doi in seen_doi:
                continue
            if doi:
                seen_doi.add(doi)
            unique.append(p)

        # Merge metadata (groups by title, merges fields, dedups)
        merged = self._merge_metadata(unique)

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

                # Merge hit_channels
                base_channels = set(base.get("hit_channels", []))
                other_channels = set(other.get("hit_channels", []))
                base["hit_channels"] = list(base_channels | other_channels)

            merged.append(base)

        # Multi-hit logging
        hit_counts = {}
        for p in merged:
            channels = p.get("hit_channels", [])
            if channels:
                n = len(channels)
                hit_counts[n] = hit_counts.get(n, 0) + 1
        if hit_counts:
            logger.info("multi_hit counts: %s", hit_counts)

        return merged


# ---------------------------------------------------------------------------
# Helper functions for query expansion and arXiv search
# ---------------------------------------------------------------------------
def auto_quote_terms(query: str) -> str:
    """通用引号封装（Fix 1：多词术语 + 含连字符术语统一加引号）。"""
    if query.startswith('"') and query.endswith('"'):
        return query
    words = query.split()
    if len(words) <= 1 and "-" not in query:
        return query
    return f'"{query}"'


def infer_arxiv_category(
    query: str,
    topic: str,
    domain_cat_map: dict,
    fallback: str = "cs.AI",
) -> str:
    """根据 query+topic 关键词推断 arXiv 分类。"""
    combined = f"{query} {topic}".lower()
    for keyword, cat in domain_cat_map.items():
        if keyword in combined:
            return cat
    return fallback


def dual_channel_arxiv_search(
    arxiv_tool: "ArxivSearch",
    query: str,
    cat_filter: str = "",
    config: "SearchConfig | None" = None,
) -> list["Paper"]:
    """arXiv 双通道检索：ti 精准 + abs 召回。"""
    from agent.tools.models import Paper

    quoted = auto_quote_terms(query)
    papers: list[Paper] = []

    # Channel 1: ti
    ti_query = f"ti:{quoted}"
    if cat_filter:
        ti_query += f" AND cat:{cat_filter}"

    ti_result = arxiv_tool.execute({
        "query": ti_query,
        "max_results": config.arxiv_ti_max_results if config else 20,
    })
    if ti_result.success:
        for p_data in ti_result.data.get("papers", []):
            paper = Paper.from_dict(p_data)
            paper.hit_channels.append("arxiv_ti")
            paper.search_source_queries.append(query)
            papers.append(paper)

    # Channel 2: abs
    abs_query = f"abs:{quoted}"
    if cat_filter:
        abs_query += f" AND cat:{cat_filter}"

    abs_result = arxiv_tool.execute({
        "query": abs_query,
        "max_results": config.arxiv_abs_max_results if config else 20,
    })
    if abs_result.success:
        for p_data in abs_result.data.get("papers", []):
            paper = Paper.from_dict(p_data)
            paper.hit_channels.append("arxiv_abs")
            paper.search_source_queries.append(query)
            papers.append(paper)

    # Dedup
    seen = set()
    unique = []
    for p in papers:
        key = p.title.lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(p)

    logger.info(
        "arXiv dual-channel [ti=%s] [abs=%s] → %d unique papers",
        "success" if ti_result.success else "fail",
        "success" if abs_result.success else "fail",
        len(unique),
    )
    return unique


# ---------------------------------------------------------------------------
# Fallback Manager
# ---------------------------------------------------------------------------
class FallbackManager:
    """分阶段 Fallback 策略。"""

    def __init__(
        self,
        arxiv_tool: "ArxivSearch",
        ss_tool: "SemanticScholarSearch | None",
        config: "SearchConfig",
    ):
        self.arxiv_tool = arxiv_tool
        self.ss_tool = ss_tool
        self.config = config

    def fallback_phase6(
        self,
        papers: list["Paper"],
        topic: str,
        keywords: list[str],
    ) -> list["Paper"]:
        """Phase 6 Fallback：论文数 < 10 时触发。"""
        from agent.tools.models import Paper

        logger.warning(
            "Phase6 fallback triggered: %d papers < %d",
            len(papers), self.config.fallback_phase6_min_papers,
        )

        queries = [topic] + keywords[:3]

        # Add survey reverse query and methodology query
        survey_query = f'"survey {topic}" OR "review {topic}"'
        queries.append(survey_query)
        method_query = f'"{topic} method" OR "{topic} approach" OR "{topic} technique"'
        queries.append(method_query)

        new_papers: list[Paper] = []

        for q in queries:
            ti_result = self.arxiv_tool.execute({
                "query": f"ti:{q}",
                "max_results": self.config.arxiv_ti_max_results,
            })
            if ti_result.success:
                for p in ti_result.data.get("papers", []):
                    paper = Paper.from_dict(p)
                    paper.hit_channels.append("fallback_phase6_ti")
                    new_papers.append(paper)

            abs_result = self.arxiv_tool.execute({
                "query": f"abs:{q}",
                "max_results": self.config.arxiv_abs_max_results,
            })
            if abs_result.success:
                for p in abs_result.data.get("papers", []):
                    paper = Paper.from_dict(p)
                    paper.hit_channels.append("fallback_phase6_abs")
                    new_papers.append(paper)

        # Dedup merge
        seen = set()
        merged = []
        for p in papers + new_papers:
            key = p.title.lower().strip()
            if key and key not in seen:
                seen.add(key)
                merged.append(p)

        logger.info("Phase6 fallback: %d -> %d papers", len(papers), len(merged))
        return merged

    def fallback_phase7(self, papers: list["Paper"], topic: str) -> list["Paper"]:
        """Phase 7 Fallback：论文数 < 5 时触发。

        Fix 4：仅 arXiv all: 单通道，max_results=20。
        """
        from agent.tools.models import Paper

        logger.warning(
            "Phase7 fallback triggered: %d papers < %d",
            len(papers), self.config.fallback_phase7_min_papers,
        )

        result = self.arxiv_tool.execute({
            "query": topic,
            "max_results": self.config.fallback_phase7_max_results,
        })

        new_papers: list[Paper] = []
        if result.success:
            for p in result.data.get("papers", []):
                paper = Paper.from_dict(p)
                paper.hit_channels.append("fallback_phase7_all")
                new_papers.append(paper)

        seen = {p.title.lower().strip() for p in papers if p.title}
        merged = list(papers)
        for p in new_papers:
            key = p.title.lower().strip()
            if key and key not in seen:
                seen.add(key)
                merged.append(p)

        logger.info("Phase7 fallback: %d -> %d papers", len(papers), len(merged))
        return merged


# ---------------------------------------------------------------------------
# Year-Segmented Semantic Scholar Search
# ---------------------------------------------------------------------------
def segmented_ss_search(
    ss_tool: "SemanticScholarSearch",
    query: str,
    config: "SearchConfig",
    topic: str = "",
) -> list["Paper"]:
    """Execute three parallel SS searches per query with year-segmented thresholds.

    Each segment gets its own year range and minCitationCount.
    Papers are tagged with hit_channel = "ss_frontier", "ss_mid", "ss_foundational".
    """
    from agent.tools.models import Paper

    all_papers: list[Paper] = []
    for segment in config.ss_year_segments:
        label = segment["label"]
        max_results_key = f"ss_{label}_max_results"
        max_results = getattr(config, max_results_key, config.ss_max_results)
        result = ss_tool.execute({
            "query": query,
            "max_results": max_results,
            "year_start": segment["start"],
            "year_end": segment["end"],
            "min_citation_count": segment["min_citation_count"],
        })
        if result.success:
            for p_data in result.data.get("papers", []):
                paper = Paper.from_dict(p_data)
                paper.hit_channels.append(f"ss_{label}")
                paper.search_source_queries.append(query)
                all_papers.append(paper)

    return all_papers


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