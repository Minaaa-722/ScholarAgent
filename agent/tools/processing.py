from agent.tools.base import Tool, ToolResult, _dedup_by_title
from agent.tools.models import Paper
from agent.core.config import SearchConfig


import logging
import os
logger = logging.getLogger(__name__)


class PdfDownload(Tool):
    name = "pdf_download"
    description = "Download paper PDF from URL"

    def execute(self, params: dict) -> ToolResult:
        url = params.get("url", "")
        save_path = params.get("save_path", "")
        if not url or not save_path:
            return ToolResult(success=False, error="url and save_path are required")
        try:
            import requests
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            resp = requests.get(url, timeout=30, headers={
                "User-Agent": "ScholarAgent/1.0"
            })
            resp.raise_for_status()
            with open(save_path, "wb") as f:
                f.write(resp.content)
            logger.info("PDF downloaded: %s (%d bytes)", save_path, len(resp.content))
            return ToolResult(success=True, data={
                "url": url,
                "save_path": save_path,
                "downloaded": True,
                "size_bytes": len(resp.content),
            })
        except Exception as e:
            logger.warning("PDF download failed for %s: %s", url, e)
            return ToolResult(success=False, error=str(e))


class PdfParse(Tool):
    name = "pdf_parse"
    description = "Parse PDF to extract full text page by page"

    def execute(self, params: dict) -> ToolResult:
        pdf_path = params.get("pdf_path", "")
        if not pdf_path:
            return ToolResult(success=False, error="pdf_path is required")
        if not os.path.exists(pdf_path):
            return ToolResult(success=False, error=f"PDF not found: {pdf_path}")
        try:
            import fitz
            doc = fitz.open(pdf_path)
            full_text_parts = []
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text = page.get_text("text").strip()
                full_text_parts.append(text)
            doc.close()
            full_text = "".join(full_text_parts)
            logger.info("PDF parsed: %s (%d pages, %d chars)", pdf_path, len(doc), len(full_text))
            return ToolResult(success=True, data={
                "pdf_path": pdf_path,
                "full_text": full_text,
                "page_count": len(doc),
            })
        except ImportError:
            return ToolResult(success=False, error="PyMuPDF (fitz) not installed. Run: pip install pymupdf")
        except Exception as e:
            logger.warning("PDF parse failed for %s: %s", pdf_path, e)
            return ToolResult(success=False, error=str(e))


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
    description = "Generate IEEEtran-standard BibTeX citation"

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


# ---------------------------------------------------------------------------
# Paper ranking
# ---------------------------------------------------------------------------
def rank_papers(papers: list["Paper"], config: "SearchConfig") -> list["Paper"]:
    """RRF + 综合加权排序。"""
    if not papers:
        return papers

    max_citations = max(p.citation_count for p in papers) or 1
    current_year = 2026

    for p in papers:
        citation_score = p.citation_count / max_citations

        if p.relevance == "strong":
            relevance_score = 1.0
        elif p.relevance == "weak":
            relevance_score = 0.5
        else:
            relevance_score = 0.0

        age = current_year - p.year
        recency_score = max(0.0, 1.0 - age / 10.0) if p.year > 0 else 0.0

        p.composite_score = round(
            config.rank_alpha * citation_score
            + config.rank_beta * relevance_score
            + config.rank_gamma * recency_score,
            4,
        )

    if config.rrf_enabled and len(papers) > 1:
        papers = _apply_rrf(papers, config)

    papers.sort(key=lambda p: p.composite_score, reverse=True)

    if papers:
        logger.info("Ranked top-3: %s", [(p.title[:40], p.composite_score) for p in papers[:3]])

    return papers


def _apply_rrf(papers: list["Paper"], config: "SearchConfig") -> list["Paper"]:
    """Reciprocal Rank Fusion 融合多通道排序。"""
    channels: dict[str, list["Paper"]] = {}
    for p in papers:
        for ch in p.hit_channels:
            channels.setdefault(ch, []).append(p)

    if not channels:
        return papers

    rrf_k = config.rrf_k
    score_map: dict[str, float] = {}

    for ch, ch_papers in channels.items():
        for rank, p in enumerate(ch_papers):
            key = p.title.lower().strip()
            score_map[key] = score_map.get(key, 0.0) + 1.0 / (rrf_k + rank)

    for p in papers:
        key = p.title.lower().strip()
        rrf_score = score_map.get(key, 0.0)
        p.composite_score = round(p.composite_score * 0.7 + rrf_score * 0.3, 4)

    return papers
