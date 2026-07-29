"""Paper availability validator for the evidence acquisition layer.

Validates paper metadata, checks arXiv status, normalizes PDF URLs,
and computes the evidence level available for each paper.
"""

import logging
import re
from typing import Optional

import requests

from agent.evidence.paper_types import (
    EvidenceLevel,
    PaperAvailability,
    PaperStatus,
)

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


class PaperAvailabilityValidator:
    """Validates paper metadata and determines available evidence level.

    For each paper:
      1. Checks metadata availability (paper_id, title, etc.)
      2. Checks abstract availability
      3. If arxiv_id: checks arXiv page for withdrawn/removed status
      4. Validates and normalizes PDF URL
      5. Computes evidence level based on what's available

    Does NOT download PDFs — that's the responsibility of EvidenceAcquisitionRouter.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self, paper: dict) -> PaperAvailability:
        """Validate a single paper and return its availability status.

        Args:
            paper: Paper metadata dict with keys: paper_id, arxiv_id,
                   pdf_url, abstract, source.

        Returns:
            PaperAvailability with status, evidence_level, and reason.
        """
        if not paper:
            return PaperAvailability(
                paper_id="",
                status=PaperStatus.UNKNOWN,
                reason="Empty paper metadata",
                evidence_level=EvidenceLevel.NONE,
            )

        paper_id = paper.get("paper_id") or paper.get("arxiv_id", "")
        arxiv_id = paper.get("arxiv_id") or ""
        pdf_url = paper.get("pdf_url") or ""
        abstract = paper.get("abstract") or ""

        metadata_available = bool(paper_id)
        abstract_available = bool(abstract and abstract.strip())

        pdf_url = self.normalize_pdf_url(pdf_url, arxiv_id)
        fulltext_available = bool(pdf_url)

        # Check arXiv status if this is an arXiv paper
        status = PaperStatus.AVAILABLE
        reason = ""
        if arxiv_id:
            arxiv_status = self._check_arxiv_status(arxiv_id)
            if arxiv_status == PaperStatus.WITHDRAWN:
                status = PaperStatus.WITHDRAWN
                reason = f"arXiv paper {arxiv_id} has been withdrawn"
                fulltext_available = False
            elif arxiv_status == PaperStatus.UNKNOWN:
                # arXiv check failed — still allow PDF attempt
                status = PaperStatus.AVAILABLE
                reason = "arXiv status check failed, proceeding with PDF"
        elif pdf_url:
            status = PaperStatus.PDF_AVAILABLE
            reason = "PDF URL available"
        else:
            if abstract_available:
                status = PaperStatus.AVAILABLE
                reason = "Abstract available, no PDF URL"
            else:
                status = PaperStatus.UNKNOWN
                reason = "No PDF URL and no abstract"

        if status != PaperStatus.WITHDRAWN and fulltext_available:
            status = PaperStatus.PDF_AVAILABLE
            reason = "PDF URL available"

        evidence_level = self.compute_evidence_level(
            metadata_available=metadata_available,
            abstract_available=abstract_available,
            fulltext_available=fulltext_available,
        )

        # Override: withdrawn papers get METADATA at most
        if status == PaperStatus.WITHDRAWN:
            evidence_level = EvidenceLevel.METADATA

        result = PaperAvailability(
            paper_id=paper_id,
            metadata_available=metadata_available,
            abstract_available=abstract_available,
            fulltext_available=fulltext_available,
            status=status,
            reason=reason,
            evidence_level=evidence_level,
        )

        logger.info(
            "[PAPER_VALIDATION] paper_id=%s status=%s evidence_level=%s reason=%s",
            paper_id, status.value, evidence_level.name, reason,
        )

        return result

    def validate_many(self, papers: list[dict]) -> list[PaperAvailability]:
        """Validate multiple papers.

        Args:
            papers: List of paper metadata dicts.

        Returns:
            List of PaperAvailability objects, one per paper.
        """
        return [self.validate(p) for p in papers]

    # ------------------------------------------------------------------
    # arXiv status check
    # ------------------------------------------------------------------

    def _check_arxiv_status(self, arxiv_id: str) -> PaperStatus:
        """Check if an arXiv paper has been withdrawn.

        Fetches the arXiv abstract page and checks for withdrawal markers.

        Args:
            arxiv_id: arXiv paper ID (e.g., "2503.18681").

        Returns:
            PaperStatus.WITHDRAWN if withdrawn, PaperStatus.AVAILABLE if OK,
            PaperStatus.UNKNOWN if check failed.
        """
        try:
            url = f"https://arxiv.org/abs/{arxiv_id}"
            resp = requests.get(url, timeout=15, allow_redirects=True)
            resp.raise_for_status()
            text = resp.text.lower()

            for pattern in _ARXIV_WITHDRAWN_PATTERNS:
                if re.search(pattern, text, re.IGNORECASE):
                    logger.info(
                        "[TRACE][PAPER_STATUS] paper_id=%s status=WITHDRAWN reason='%s'",
                        arxiv_id, pattern,
                    )
                    return PaperStatus.WITHDRAWN

            return PaperStatus.AVAILABLE

        except Exception as e:
            logger.warning(
                "arXiv status check failed for %s: %s", arxiv_id, e
            )
            return PaperStatus.UNKNOWN

    # ------------------------------------------------------------------
    # PDF URL normalization
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_pdf_url(url: str, arxiv_id: Optional[str]) -> str:
        """Normalize a PDF URL to a canonical form.

        Rules:
          - If arxiv_id is present, use canonical:
            https://arxiv.org/pdf/{id}.pdf
          - If URL is an arxiv PDF URL without .pdf extension, add .pdf
          - Otherwise, return URL as-is (or empty string)

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

    # ------------------------------------------------------------------
    # Evidence level computation
    # ------------------------------------------------------------------

    @staticmethod
    def compute_evidence_level(
        metadata_available: bool,
        abstract_available: bool,
        fulltext_available: bool,
    ) -> EvidenceLevel:
        """Compute the highest evidence level available.

        Args:
            metadata_available: Whether paper metadata exists.
            abstract_available: Whether the abstract is accessible.
            fulltext_available: Whether full text (PDF) is accessible.

        Returns:
            The highest EvidenceLevel achievable.
        """
        if fulltext_available:
            return EvidenceLevel.FULL_TEXT
        if abstract_available:
            return EvidenceLevel.ABSTRACT
        if metadata_available:
            return EvidenceLevel.METADATA
        return EvidenceLevel.NONE