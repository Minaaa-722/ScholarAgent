"""PDF parsing and chunk filtering for the evidence grounding layer.

Provides PDFChunk dataclass for representing extracted text segments,
PDFParser for splitting PDFs into page-level chunks with section heading
detection, and ChunkFilter for filtering chunks by evidence category.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PDFChunk:
    """A single chunk of text extracted from a PDF."""

    paper_id: str
    chunk_id: str
    page_number: int
    section: str = ""
    content: str = ""


# ---------------------------------------------------------------------------
# Section heading patterns (ordered by specificity)
# ---------------------------------------------------------------------------
_SECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\d+\.\s+[A-Z]"),                     # "1. Introduction"
    re.compile(r"^\d+\.\d+\s+[A-Z]"),                   # "1.1 Related Work"
    re.compile(r"^(?:Abstract|Introduction|Related Work|Method|Approach|Experiments?|Results|Conclusion|Discussion|References|Appendix|Acknowledgments)\b", re.IGNORECASE),  # Named sections
    re.compile(r"^[A-Z][A-Z\s]{2,}$"),                  # "METHODOLOGY" (all-caps)
    re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*$"),   # "Related Work" (title case line)
]


class PDFParser:
    """Parse PDF files into page-level chunks with section detection.

    Uses PyMuPDF (fitz) to extract text page by page and attempts to
    detect section headings via regex heuristics.
    """

    def parse(self, paper_id: str, pdf_path: str) -> list[PDFChunk]:
        """Parse a PDF into a list of PDFChunk objects.

        Args:
            paper_id: Unique identifier for the paper.
            pdf_path: Filesystem path to the PDF file.

        Returns:
            List of PDFChunk objects, one per page, with section
            headings detected via regex heuristics.
        """
        import fitz

        chunks: list[PDFChunk] = []
        doc = fitz.open(pdf_path)

        try:
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text = page.get_text("text").strip()
                if not text:
                    continue

                section = self._detect_section(text)

                chunk = PDFChunk(
                    paper_id=paper_id,
                    chunk_id=f"{paper_id}_p{page_num + 1}",
                    page_number=page_num + 1,
                    section=section,
                    content=text,
                )
                chunks.append(chunk)
        finally:
            doc.close()

        logger.info("Parsed %d chunks from %s", len(chunks), pdf_path)
        return chunks

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_section(text: str) -> str:
        """Attempt to detect a section heading from the first text line.

        Returns the detected section name or an empty string if no
        heading is matched.
        """
        first_line = text.split("\n", 1)[0].strip()
        if not first_line:
            return ""

        for pattern in _SECTION_PATTERNS:
            match = pattern.search(first_line)
            if match:
                # Return the full matched heading text
                return match.group(0).strip()

        return ""


class ChunkFilter:
    """Filter PDF chunks by evidence category using keyword heuristics."""

    CATEGORY_KEYWORDS: dict[str, list[str]] = {
        "architecture": [
            "architecture", "encoder", "decoder", "transformer",
            "backbone", "layer", "block", "module", "attention",
        ],
        "benchmark": [
            "benchmark", "accuracy", "score", "bleu", "rouge",
            "f1", "state-of-the-art", "sota", "dataset",
        ],
        "dataset": [
            "dataset", "corpus", "benchmark", "data collection",
        ],
        "training": [
            "train", "learning rate", "optimizer", "loss",
            "gradient", "epoch", "batch size",
        ],
        "limitation": [
            "limitation", "drawback", "failure", "error",
            "challenge", "future work", "limitation",
        ],
    }

    def filter(self, chunks: list[PDFChunk], category: str) -> list[PDFChunk]:
        """Filter chunks by whether they contain keywords for a category.

        Args:
            chunks: List of PDFChunk objects to filter.
            category: Evidence category name. Must be a key in
                      CATEGORY_KEYWORDS.

        Returns:
            Filtered list of chunks whose content contains at least one
            keyword for the given category.
        """
        keywords = self.CATEGORY_KEYWORDS.get(category, [])
        if not keywords:
            return []

        pattern = re.compile(
            "|".join(re.escape(kw) for kw in keywords),
            re.IGNORECASE,
        )

        return [c for c in chunks if pattern.search(c.content)]