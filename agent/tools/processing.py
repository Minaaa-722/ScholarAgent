from agent.tools.base import Tool, ToolResult, _dedup_by_title


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
