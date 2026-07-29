"""Processing tools for PDF download, parsing, and paper metadata handling.

Enhanced with:
- normalize_pdf_url(): canonical URL normalization
- check_arxiv_status(): withdrawal detection before download
- PDF download with timeout=15, non-raising error handling
- Structured error responses for pipeline integration
"""

from agent.tools.base import Tool, ToolResult, _dedup_by_title

import logging
import os
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# arXiv withdrawal markers (case-insensitive check)
_ARXIV_WITHDRAWN_PATTERNS = [
    r"withdrawn",
    r"withdrawn paper",
    r"has been removed",
    r"unavailable",
    r"this paper has been withdrawn",
    r"this article has been withdrawn",
]


# ---------------------------------------------------------------------------
# URL normalization
# ---------------------------------------------------------------------------

def normalize_pdf_url(url: str, arxiv_id: Optional[str] = None) -> str:
    """Normalize a PDF URL to a canonical form.

    Rules:
      - If arxiv_id is present, use canonical: https://arxiv.org/pdf/{id}.pdf
      - If URL is an arxiv PDF URL without .pdf extension, add .pdf
      - Otherwise, return URL as-is (or empty string if URL is empty)

    Args:
        url: The original PDF URL.
        arxiv_id: Optional arXiv paper ID.

    Returns:
        Normalized PDF URL string.
    """
    if not url:
        return ""

    # If we have an arxiv_id, always prefer the canonical URL
    if arxiv_id:
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    # If it's an arxiv URL without .pdf, add it
    stripped = url.rstrip("/")
    if "arxiv.org/pdf/" in stripped and not stripped.endswith(".pdf"):
        return stripped + ".pdf"

    return url


# ---------------------------------------------------------------------------
# arXiv status check
# ---------------------------------------------------------------------------

def check_arxiv_status(arxiv_id: str) -> dict:
    """Check if an arXiv paper has been withdrawn or is unavailable.

    Args:
        arxiv_id: arXiv paper ID (e.g., "2503.18681").

    Returns:
        Dict with keys:
          - status: "AVAILABLE", "WITHDRAWN", or "UNKNOWN"
          - reason: Human-readable explanation
    """
    if not arxiv_id:
        return {"status": "UNKNOWN", "reason": "No arxiv_id provided"}

    try:
        url = f"https://arxiv.org/abs/{arxiv_id}"
        resp = requests.get(url, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        text = resp.text.lower()

        for pattern in _ARXIV_WITHDRAWN_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.info(
                    "[TRACE][PAPER_STATUS] arxiv_id=%s status=WITHDRAWN reason='%s'",
                    arxiv_id, pattern,
                )
                return {"status": "WITHDRAWN", "reason": f"arXiv paper {arxiv_id} has been withdrawn"}

        return {"status": "AVAILABLE", "reason": "arXiv paper is available"}

    except Exception as e:
        logger.warning("arXiv status check failed for %s: %s", arxiv_id, e)
        return {"status": "UNKNOWN", "reason": f"arXiv status check failed: {e}"}


# ---------------------------------------------------------------------------
# PDF Download
# ---------------------------------------------------------------------------

class PdfDownload(Tool):
    name = "pdf_download"
    description = "Download paper PDF from URL"

    def execute(self, params: dict) -> ToolResult:
        url = params.get("url", "")
        save_path = params.get("save_path", "")
        arxiv_id = params.get("arxiv_id", "")

        if not url and not arxiv_id:
            return ToolResult(success=False, error="url or arxiv_id is required")
        if not save_path:
            return ToolResult(success=False, error="save_path is required")

        # Normalize URL
        url = normalize_pdf_url(url, arxiv_id)

        # Check arXiv status before downloading
        if arxiv_id:
            status = check_arxiv_status(arxiv_id)
            if status["status"] == "WITHDRAWN":
                logger.warning("Skipping download for withdrawn paper %s", arxiv_id)
                return ToolResult(
                    success=False,
                    error=f"Paper {arxiv_id} has been withdrawn from arXiv",
                    data={"status": "WITHDRAWN", "reason": status["reason"]},
                )

        try:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            resp = requests.get(
                url,
                timeout=15,
                allow_redirects=True,
                headers={"User-Agent": "ScholarAgent/1.0"},
            )
            resp.raise_for_status()
            with open(save_path, "wb") as f:
                f.write(resp.content)
            logger.info(
                "PDF downloaded: %s (%d bytes)", save_path, len(resp.content)
            )
            return ToolResult(success=True, data={
                "url": url,
                "save_path": save_path,
                "downloaded": True,
                "size_bytes": len(resp.content),
                "status": "PDF_AVAILABLE",
            })
        except requests.exceptions.Timeout as e:
            logger.warning("PDF download timed out for %s: %s", url, e)
            return ToolResult(
                success=False,
                error="timeout",
                data={"status": "PDF_UNAVAILABLE", "reason": f"Download timed out: {e}"},
            )
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else "unknown"
            logger.warning("PDF download HTTP error for %s: %s", url, e)
            return ToolResult(
                success=False,
                error=f"HTTP {status_code}",
                data={"status": "PDF_UNAVAILABLE", "reason": f"HTTP {status_code}"},
            )
        except Exception as e:
            logger.warning("PDF download failed for %s: %s", url, e)
            return ToolResult(
                success=False,
                error=str(e),
                data={"status": "PDF_UNAVAILABLE", "reason": str(e)},
            )


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
            logger.info(
                "PDF parsed: %s (%d pages, %d chars)",
                pdf_path, len(doc), len(full_text),
            )
            return ToolResult(success=True, data={
                "pdf_path": pdf_path,
                "full_text": full_text,
                "page_count": len(doc),
            })
        except ImportError:
            return ToolResult(
                success=False,
                error="PyMuPDF (fitz) not installed. Run: pip install pymupdf",
            )
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